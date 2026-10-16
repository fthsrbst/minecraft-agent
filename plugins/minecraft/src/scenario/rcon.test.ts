import { describe, expect, it } from "vitest";

import { decodePackets, encodePacket, PacketType, RconError } from "./rcon.js";

describe("RCON packets", () => {
  it("round-trips a packet", () => {
    const packet = { id: 7, type: PacketType.Command, body: "time set day" };
    const { packets, rest } = decodePackets(encodePacket(packet));
    expect(packets).toEqual([packet]);
    expect(rest.length).toBe(0);
  });

  it("uses the documented layout", () => {
    const bytes = encodePacket({ id: 1, type: PacketType.Auth, body: "pw" });
    expect(bytes.readInt32LE(0)).toBe(12); // id + type + "pw" + two NULs
    expect(bytes.readInt32LE(4)).toBe(1);
    expect(bytes.readInt32LE(8)).toBe(PacketType.Auth);
    expect(bytes.subarray(12).toString("hex")).toBe("70770000");
  });

  it("keeps a partial packet for the next chunk", () => {
    const whole = Buffer.concat([
      encodePacket({ id: 1, type: 0, body: "a" }),
      encodePacket({ id: 2, type: 0, body: "bb" }),
    ]);
    const first = decodePackets(whole.subarray(0, 20));
    expect(first.packets.map((p) => p.body)).toEqual(["a"]);
    const second = decodePackets(Buffer.concat([first.rest, whole.subarray(20)]));
    expect(second.packets.map((p) => p.body)).toEqual(["bb"]);
    expect(second.rest.length).toBe(0);
  });

  it.each([-8, 0, 9, 5000])("rejects a corrupt length %i instead of looping", (length) => {
    const bytes = Buffer.alloc(16);
    bytes.writeInt32LE(length, 0);
    expect(() => decodePackets(bytes)).toThrow(RconError);
  });
});
