"""MCP boundary for the complete remix build/render/compare loop."""

from .remix_assets import project, project_lock
from .remix_live import build, inspect_project, prepare, worker
from .remix_preview import capture


def register_remix_session(mcp, dispatch):
    @mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
    def inspect_remix_session(project_dir: str) -> dict:
        """Inspect a private remix journal, owned track identities and current source
        fingerprints without edits. Report stale bindings and uncertain partial creates;
        never adopt or delete an unverified track automatically.
        """
        return inspect_project(dispatch, project_dir)

    @mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": False})
    def prepare_remix_session(
        config: dict,
        sources: dict,
        project_dir: str,
        infer_vocals: bool = True,
        refresh_pulses: bool = False,
    ) -> dict:
        """Bind selected riff_midi/riff/vocal/rock_context clips with fresh name/start guards,
        render immutable private audio assets, and save a rebuildable plan. Each source:
        {target:{track_index,clip_index,clip_view,expected_track_name,expected_clip_name,
        expected_start_time},source_start?:number}. source_start uses clip beats if warped,
        seconds otherwise. Optional timing_reference is a guarded audio target sharing
        the correct Warp map across aligned stems; source_offset_seconds is a measured
        constant correction within +/-2 seconds. No Live writes. Optional level-based vocal activity inference;
        refresh_pulses reads the owned Session Pulse Input MIDI. See REMIX_V2_PLAN.md.
        """
        return prepare(dispatch, config, sources, project_dir, infer_vocals, refresh_pulses)

    @mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": True})
    def build_remix_session(
        project_dir: str, drum_kit: str = "808 Core Kit", drum_map: dict | None = None
    ) -> dict:
        """Build/update only this private project's named owned tracks in Live. Recheck sources,
        map the loaded kit's actual pads, create native instruments and bounded automation,
        and verify MIDI/Arrangement readback. New tracks start muted. Same bounds on rebuild;
        source tracks stay intact. Requires stopped transport and matching tempo. Partial
        failures retain a journal and are never blindly replayed. No automatic save.
        """
        return build(dispatch, project_dir, drum_kit, drum_map)

    @mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": True})
    def preview_remix_session(
        project_dir: str, bars: int = 8, include_lead_in: bool = True
    ) -> dict:
        """Capture a <=60 second preview of owned remix lanes through Live Resampling;
        temporarily isolate them, disarm others, disable monitoring/feedback and verify
        transport after start. Restore original mixer/arm/loop/time state. Returns WAV,
        measured loudness/peaks/low-band correlation and a bounded problem scan. Requires
        stopped playback and no launched Session clips. Real-time capture is not audition.
        """
        return capture(dispatch, project_dir, bars, include_lead_in)

    @mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": False})
    def compare_remix_previews(project_dir: str, reference: str, variant: str) -> dict:
        """Create A/B WAVs matched by measured integrated LUFS, or explicitly labeled RMS
        fallback. Attenuate only, preserve source files, refuse mismatched durations.
        Returns source/variant measurements and gain adjustments; no preference claim.
        """
        root, _ = project(project_dir)
        with project_lock(root):
            return worker("compare", root, reference=reference, variant=variant)
