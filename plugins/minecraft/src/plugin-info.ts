/** Identity the plugin reports to the core during the handshake (protocol arrives in P1.4). */
export const PLUGIN_ID = "minecraft";

/** The only Minecraft Java version this plugin supports (AGENTS.md decision 3). */
export const GAME_VERSION = "1.21.11";

export interface PluginInfo {
  readonly id: string;
  readonly gameVersion: string;
}

export function pluginInfo(): PluginInfo {
  return { id: PLUGIN_ID, gameVersion: GAME_VERSION };
}
