from pathlib import Path


class ReleaseNotesError(ValueError):
    pass


MAX_RELEASE_NOTE_ITEMS = 5
MAX_RELEASE_NOTE_LENGTH = 160


def release_notes_for_deployment(path):
    """Read the short, user-facing notes prepared for the next deployment."""
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise ReleaseNotesError(f"Could not read release notes: {error}") from error

    try:
        start = next(
            index
            for index, line in enumerate(lines)
            if line.strip().lower() == "## next deployment"
        )
    except StopIteration as error:
        raise ReleaseNotesError(
            "RELEASE_NOTES.md needs a '## Next deployment' section."
        ) from error

    notes = []
    for line in lines[start + 1 :]:
        if line.startswith("## "):
            break
        stripped = line.strip()
        if stripped.startswith("- "):
            note = stripped[2:].strip()
            if note:
                notes.append(note)

    if not notes:
        raise ReleaseNotesError(
            "RELEASE_NOTES.md needs at least one bullet under '## Next deployment'."
        )
    if len(notes) > MAX_RELEASE_NOTE_ITEMS or any(
        len(note) > MAX_RELEASE_NOTE_LENGTH for note in notes
    ):
        raise ReleaseNotesError(
            "Release notes must have at most five bullets of 160 characters each."
        )
    if any(note.lower() in {"todo", "tbd"} for note in notes):
        raise ReleaseNotesError("Release notes must describe the deployed change.")
    return notes
