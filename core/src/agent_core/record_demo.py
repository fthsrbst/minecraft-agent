"""P4.1 check: verify a recorded skill by replaying it in fresh spots.

    uv run --env-file ../.env python -m agent_core.record_demo ../plugins/<game> RECORDING.json \\
        [--runs 5] [--library runs/skills.sqlite] [--no-save]

A recording comes from `#record start` / `#record stop <name>` in the agent (runs/recordings/).
Each replay: the scenario component prepares a fresh spot facing another way and gives the
materials; the bot runs the skill; the plugin's structure check decides. The skill enters the
library when at least 60% of the replays pass. One run record per replay in runs/recordings.jsonl.
"""

import argparse
import asyncio
import sys
from pathlib import Path

from agent_core.library import LibraryError, SkillLibrary
from agent_core.plugins import ManifestError, PluginClient, PluginError
from agent_core.recording.skill import RecordedSkill, RecordingError
from agent_core.recording.verify import verify
from agent_core.runs import RunRecorder

RUNS_PATH = Path("runs/recordings.jsonl")
TELEMETRY_PATH = Path("runs/telemetry/agent.jsonl")


async def run(args: argparse.Namespace) -> bool:
    skill = RecordedSkill.load(args.recording)
    print(f"{skill.card.name}: {skill.summary}")
    if skill.unsupported:
        print(f"  not captured: {'; '.join(skill.unsupported)}")
    library = None if args.no_save else SkillLibrary(args.library)
    try:
        async with await PluginClient.start(args.plugin_dir, component="scenario") as scenario:
            await scenario.handshake(timeout_s=15)
            async with await PluginClient.start(args.plugin_dir) as bot:
                await bot.handshake()
                result = await verify(
                    skill,
                    bot,
                    scenario,
                    runs=args.runs,
                    library=library,
                    recorder=RunRecorder(RUNS_PATH),
                    telemetry_path=TELEMETRY_PATH,
                )
    finally:
        if library is not None:
            library.close()
    for replay in result.replays:
        print(
            f"  replay {replay.index} facing {replay.facing}: {replay.verdict} "
            f"({replay.matched}/{replay.total} cells; skill {replay.skill_status}"
            + (f": {replay.error}" if replay.error else "")
            + ")"
            + (f" missing {list(replay.missing)[:3]}" if replay.missing else "")
        )
    print(
        f"{result.passed}/{len(result.replays)} replays verified; "
        + ("saved to the library" if result.saved else "not saved")
    )
    return result.saved or (args.no_save and result.passed == len(result.replays))


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify a recorded skill by replaying it.")
    parser.add_argument("plugin_dir", type=Path)
    parser.add_argument("recording", type=Path)
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--library", type=Path, default=Path("runs/skills.sqlite"))
    parser.add_argument("--no-save", action="store_true", help="verify only, never store")
    args = parser.parse_args()
    try:
        ok = asyncio.run(run(args))
    except (ManifestError, PluginError, RecordingError, LibraryError, TimeoutError) as error:
        print(f"error: {error or 'timed out'}", file=sys.stderr)
        return 1
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
