import argparse
from datetime import datetime, timezone
from email import policy
from email.parser import BytesParser
from email.utils import parseaddr, parsedate_to_datetime
import filecmp
import mailbox
import os
from pathlib import Path
import tempfile
import time


SKIP_DIR_NAMES = {"emails", "pictures", "__pycache__", "thunderbird"}


def parse_args():
    script_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(
        description=(
            "Build Thunderbird-compatible mbox files for one or more regions "
            "from generated receipt .eml files."
        )
    )
    parser.add_argument(
        "regions",
        nargs="*",
        type=Path,
        help="Region directories. Defaults to all top-level region directories in the repo.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=script_dir / "thunderbird",
        help=(
            "Directory where Thunderbird mbox files will be written. "
            "Defaults to <repo>/thunderbird."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report whether any mbox file would be rewritten.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Rewrite output files even when the generated mbox is unchanged.",
    )
    return parser.parse_args()


def iter_default_regions(base_dir, output_dir):
    output_name = output_dir.resolve().name
    for entry in sorted(base_dir.iterdir()):
        if not entry.is_dir():
            continue
        if entry.name.startswith(".") or entry.name in {"__pycache__", output_name}:
            continue
        yield entry.resolve()


def resolve_regions(base_dir, output_dir, region_args):
    if region_args:
        for region_arg in region_args:
            region_dir = region_arg.expanduser().resolve()
            if not region_dir.is_dir():
                raise SystemExit(f"Missing region directory: {region_arg}")
            yield region_dir
        return

    yield from iter_default_regions(base_dir, output_dir)


def collect_eml_paths(region_dir):
    eml_paths = []
    for root, dirnames, filenames in os.walk(region_dir):
        dirnames[:] = [
            dir_name
            for dir_name in dirnames
            if dir_name not in SKIP_DIR_NAMES and not dir_name.startswith(".")
        ]
        root_path = Path(root)
        for file_name in filenames:
            if file_name.endswith(".eml"):
                eml_paths.append(root_path / file_name)
    return sorted(eml_paths)


def parse_message(eml_path):
    return BytesParser(policy=policy.default).parsebytes(eml_path.read_bytes())


def normalize_message_datetime(msg, fallback_timestamp):
    date_header = msg.get("Date")
    if date_header:
        parsed = parsedate_to_datetime(date_header)
        if parsed is not None:
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
    return datetime.fromtimestamp(fallback_timestamp, tz=timezone.utc)


def to_mbox_message(eml_path):
    msg = parse_message(eml_path)
    sender = parseaddr(msg.get("From", ""))[1] or "MAILER-DAEMON"
    message_datetime = normalize_message_datetime(msg, eml_path.stat().st_mtime)

    mbox_message = mailbox.mboxMessage(msg)
    mbox_message.set_from(sender, time.gmtime(message_datetime.timestamp()))
    return mbox_message


def render_temp_mbox(output_path, eml_paths):
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(
        prefix=f".{output_path.name}.",
        suffix=".tmp",
        dir=output_path.parent,
        delete=False,
    ) as temp_file:
        temp_path = Path(temp_file.name)

    mbox = mailbox.mbox(temp_path, create=True)
    try:
        for eml_path in eml_paths:
            mbox.add(to_mbox_message(eml_path))
        mbox.flush()
    finally:
        mbox.close()

    return temp_path


def output_changed(output_path, temp_path):
    if not output_path.is_file():
        return True
    return not filecmp.cmp(output_path, temp_path, shallow=False)


def main():
    args = parse_args()
    script_dir = Path(__file__).resolve().parent
    output_dir = args.output_dir.expanduser().resolve()

    for region_dir in resolve_regions(script_dir, output_dir, args.regions):
        eml_paths = collect_eml_paths(region_dir)
        output_path = output_dir / region_dir.name
        if not eml_paths:
            if not output_path.exists():
                print(f"skip\t{output_path}\tno-eml")
                continue

            if args.dry_run:
                print(f"would_remove\t{output_path}")
                continue

            output_path.unlink()
            print(f"removed\t{output_path}")
            continue

        temp_path = render_temp_mbox(output_path, eml_paths)
        try:
            changed = args.force or output_changed(output_path, temp_path)

            if args.dry_run:
                status = "would_write" if changed else "skip"
                suffix = "" if changed else "\tunchanged"
                print(f"{status}\t{output_path}{suffix}")
                continue

            if not changed:
                print(f"skip\t{output_path}\tunchanged")
                continue

            temp_path.replace(output_path)
            print(f"wrote\t{output_path}")
        finally:
            if temp_path.exists():
                temp_path.unlink()


if __name__ == "__main__":
    main()
