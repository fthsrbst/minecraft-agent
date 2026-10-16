/**
 * Minimal Source RCON client (the protocol Minecraft servers speak on the RCON port).
 * Packet: int32 length, int32 id, int32 type, ASCII body, two NUL bytes; all integers little-endian.
 * Used only by the scenario component (the evaluator), never by the agent's bot.
 */
import { Socket } from "node:net";

export const PacketType = { Response: 0, Command: 2, Auth: 3 } as const;

export interface Packet {
  readonly id: number;
  readonly type: number;
  readonly body: string;
}

// Minecraft rejects command packets with bodies over 1446 bytes.
export const MAX_BODY_BYTES = 1446;

export function encodePacket({ id, type, body }: Packet): Buffer {
  const bodyBytes = Buffer.from(body, "utf8");
  const buffer = Buffer.alloc(14 + bodyBytes.length);
  buffer.writeInt32LE(10 + bodyBytes.length, 0);
  buffer.writeInt32LE(id, 4);
  buffer.writeInt32LE(type, 8);
  bodyBytes.copy(buffer, 12);
  return buffer;
}

/** Splits a byte stream into complete packets; returns them plus the unconsumed remainder. */
export function decodePackets(buffer: Buffer): { packets: Packet[]; rest: Buffer } {
  const packets: Packet[] = [];
  let offset = 0;
  while (buffer.length - offset >= 4) {
    const length = buffer.readInt32LE(offset);
    if (buffer.length - offset - 4 < length) {
      break;
    }
    const start = offset + 4;
    packets.push({
      id: buffer.readInt32LE(start),
      type: buffer.readInt32LE(start + 4),
      body: buffer.toString("utf8", start + 8, start + length - 2),
    });
    offset = start + length;
  }
  return { packets, rest: buffer.subarray(offset) };
}

export class RconError extends Error {
  override readonly name = "RconError";
}

export class RconClient {
  private nextId = 1;
  private buffer: Buffer = Buffer.alloc(0);
  private readonly waiting = new Map<number, (packet: Packet) => void>();
  private closedError: RconError | null = null;

  private constructor(
    private readonly socket: Socket,
    private readonly timeoutMs: number,
  ) {
    socket.on("data", (chunk: Buffer) => {
      const { packets, rest } = decodePackets(Buffer.concat([this.buffer, chunk]));
      this.buffer = rest;
      for (const packet of packets) {
        // A failed login answers with id -1, which matches no waiter; route it to the auth request.
        const id = packet.id === -1 ? [...this.waiting.keys()][0] : packet.id;
        if (id !== undefined) {
          this.waiting.get(id)?.(packet);
        }
      }
    });
    const fail = (error: RconError): void => {
      this.closedError ??= error;
      this.waiting.clear();
    };
    socket.on("error", (error) => {
      fail(new RconError(`RCON connection error: ${error.message}`));
    });
    socket.on("close", () => {
      fail(new RconError("RCON connection closed."));
    });
  }

  static async connect(options: {
    host: string;
    port: number;
    password: string;
    timeoutMs: number;
  }): Promise<RconClient> {
    const socket = new Socket();
    await new Promise<void>((resolve, reject) => {
      const timer = setTimeout(() => {
        socket.destroy();
        reject(
          new RconError(
            `No RCON connection to ${options.host}:${String(options.port)} within ${String(options.timeoutMs)} ms.`,
          ),
        );
      }, options.timeoutMs);
      socket.once("error", (error) => {
        clearTimeout(timer);
        reject(
          new RconError(
            `Cannot connect to RCON at ${options.host}:${String(options.port)}: ${error.message}`,
          ),
        );
      });
      socket.connect(options.port, options.host, () => {
        clearTimeout(timer);
        resolve();
      });
    });

    const client = new RconClient(socket, options.timeoutMs);
    const reply = await client.send(PacketType.Auth, options.password);
    if (reply.id === -1) {
      client.close();
      throw new RconError("RCON rejected the password; check MC_RCON_PASSWORD in .env.");
    }
    return client;
  }

  /** Runs one server command (without the leading slash) and returns the server's reply text. */
  async command(command: string): Promise<string> {
    return (await this.send(PacketType.Command, command)).body;
  }

  close(): void {
    this.socket.end();
  }

  private send(type: number, body: string): Promise<Packet> {
    if (this.closedError !== null) {
      return Promise.reject(this.closedError);
    }
    if (Buffer.byteLength(body, "utf8") > MAX_BODY_BYTES) {
      return Promise.reject(new RconError(`RCON body over ${String(MAX_BODY_BYTES)} bytes.`));
    }
    const id = this.nextId++;
    return new Promise<Packet>((resolve, reject) => {
      const timer = setTimeout(() => {
        this.waiting.delete(id);
        reject(
          new RconError(`RCON gave no answer to "${body}" within ${String(this.timeoutMs)} ms.`),
        );
      }, this.timeoutMs);
      this.waiting.set(id, (packet) => {
        // The server sends an empty RESPONSE before the AUTH reply; wait for the auth result itself.
        if (type === PacketType.Auth && packet.type !== 2) {
          return;
        }
        clearTimeout(timer);
        this.waiting.delete(id);
        resolve(packet);
      });
      this.socket.write(encodePacket({ id, type, body }));
    });
  }
}
