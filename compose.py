import argparse
from datetime import date
import hashlib
import html
import mimetypes
from email.message import EmailMessage
from pathlib import Path


DEFAULT_FROM = "twells@kipr.org"
DEFAULT_IMAGE_ANGLE = 270
DEFAULT_SIGNATURE = "Sincerely,\nThomas Wells"
OVERSIZE_WARNING_TEMPLATE = (
    '"{display_name}" seems to be larger than 220x220x250 mm. '
    "This might be fine if you scaled the part when printing, but your physical part "
    "may be measured at the event."
)


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Compose a receipt email for a single team submission directory and "
            "write it as an .eml file."
        )
    )
    parser.add_argument(
        "team_dir",
        type=Path,
        help="Directory named like TEAMNUM-TEAMNAME containing STL files and email.txt.",
    )
    parser.add_argument(
        "--from-address",
        default=DEFAULT_FROM,
        help=f"From address for the receipt email. Defaults to {DEFAULT_FROM}.",
    )
    parser.add_argument(
        "--image-angle",
        type=int,
        default=DEFAULT_IMAGE_ANGLE,
        help=f"Rendered angle to embed for each part. Defaults to {DEFAULT_IMAGE_ANGLE}.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output .eml path. Defaults to receipt-<team number>.eml inside the team directory.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report whether the receipt would be rewritten.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Rewrite the output even when the generated email is unchanged.",
    )
    return parser.parse_args()


def parse_team_dir_name(team_dir):
    team_name = team_dir.name
    if "-" not in team_name:
        raise SystemExit(
            f"Team directory must be named like <team number>-<team name>: {team_dir}"
        )
    team_number, team_label = team_name.split("-", 1)
    return team_number, team_label.replace("_", " ")


def load_recipient(team_dir):
    email_path = team_dir / "email.txt"
    if not email_path.is_file():
        raise SystemExit(f"Missing email.txt in {team_dir}")

    recipient = email_path.read_text(encoding="utf-8").strip()
    if not recipient:
        raise SystemExit(f"email.txt is empty in {team_dir}")
    return recipient


def stable_token(*parts, length=16):
    digest = hashlib.sha1()
    for part in parts:
        digest.update(str(part).encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()[:length]


def build_cid(team_number, image_angle, part_name):
    token = stable_token(team_number, image_angle, part_name)
    return f"{part_name}.{token}@local"


def load_manifest(manifest_path):
    if not manifest_path.is_file():
        return {}

    manifest = {}
    for line in manifest_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        key, sep, value = line.partition("\t")
        if not sep:
            continue
        manifest[key] = value
    return manifest


def build_oversize_warning(part):
    return OVERSIZE_WARNING_TEMPLATE.format(display_name=part["display_name"])


def collect_parts(team_dir, team_number, image_angle):
    stl_files = sorted(team_dir.glob("*.stl"))
    if not stl_files:
        raise SystemExit(f"No STL files found in {team_dir}")

    parts = []
    for stl_path in stl_files:
        image_path = team_dir / stl_path.stem / f"{image_angle}.png"
        if not image_path.is_file():
            raise SystemExit(f"Missing rendered image for {stl_path.name}: {image_path}")
        manifest = load_manifest(team_dir / stl_path.stem / ".render.tsv")
        parts.append(
            {
                "name": stl_path.stem,
                "display_name": stl_path.stem.replace("_", " "),
                "image_path": image_path,
                "cid": build_cid(team_number, image_angle, stl_path.stem),
                "oversized": manifest.get("fit_status") == "oversized",
            }
        )
    return parts


def build_plain_text(team_number, team_label, event_year, parts):
    count = len(parts)
    noun = "part" if count == 1 else "parts"
    warnings = [build_oversize_warning(part) for part in parts if part["oversized"]]
    lines = [
        f"Team {team_number} ({team_label}),",
        "",
        build_receipt_intro(count, noun, event_year),
        "",
    ]
    if warnings:
        lines.append("Warnings:")
        lines.extend(warnings)
        lines.append("")
    lines.append("Submitted parts:")
    lines.extend(f"- {part['display_name']}" for part in parts)
    lines.append("")
    lines.extend(DEFAULT_SIGNATURE.split("\n"))
    return "\n".join(lines)


def build_html_signature():
    escaped_signature = html.escape(DEFAULT_SIGNATURE)
    return escaped_signature.replace("\n", "<br>\n")


def build_receipt_intro(count, noun, event_year):
    subject = "This part" if count == 1 else "These parts"
    return (
        f"Thank you for your submission! This email certifies our receipt of the "
        f"{count} {noun} below. Pending physical measurement and the head judge's "
        f"approval, {subject.lower()} may be used at {event_year} Botball regional "
        f"events. If any submitted part is an open-source model from a "
        f"previous year, it is very likely to be approved at the event, though final "
        f"approval remains with the head judge."
    )


def build_html(team_number, team_label, event_year, parts):
    count = len(parts)
    noun = "part" if count == 1 else "parts"
    warnings = [build_oversize_warning(part) for part in parts if part["oversized"]]

    blocks = []
    for part in parts:
        blocks.append(
            (
                '<div style="margin: 0 0 24px;">'
                f'<p style="margin: 0 0 8px;"><strong>{part["display_name"]}</strong></p>'
                f'<img src="cid:{part["cid"]}" alt="{part["display_name"]}" '
                'style="max-width: 480px; height: auto; display: block;">'
                "</div>"
            )
        )

    warning_block = ""
    if warnings:
        warning_items = "".join(
            f"<li>{html.escape(warning)}</li>"
            for warning in warnings
        )
        warning_block = (
            '<div style="margin: 0 0 24px;">'
            '<p style="margin: 0 0 8px;"><strong>Warnings</strong></p>'
            f"<ul style=\"margin: 0; padding-left: 20px;\">{warning_items}</ul>"
            "</div>"
        )

    return (
        f"<p>Team {team_number} ({team_label}),</p>"
        f"<p>{html.escape(build_receipt_intro(count, noun, event_year)).replace(str(count), f'<b>{count}</b>', 1)}</p>"
        f"{warning_block}"
        f"{''.join(blocks)}"
        f"<p>{build_html_signature()}</p>"
    )


def attach_images(html_part, parts):
    for part in parts:
        image_path = part["image_path"]
        mime_type = mimetypes.guess_type(image_path.name)[0] or "application/octet-stream"
        maintype, subtype = mime_type.split("/", 1)
        html_part.add_related(
            image_path.read_bytes(),
            maintype=maintype,
            subtype=subtype,
            cid=f"<{part['cid']}>",
            disposition="inline",
            filename=f"{part['name']}-{image_path.name}",
        )


def set_boundaries(msg, html_part, team_number, team_label, recipient, from_address, image_angle, parts):
    outer_boundary = stable_token(
        "receipt",
        team_number,
        team_label,
        recipient,
        from_address,
        image_angle,
        *(part["name"] for part in parts),
        length=24,
    )
    related_boundary = stable_token(
        "images",
        *(part["cid"] for part in parts),
        length=24,
    )
    msg.set_boundary(f"receipt-{outer_boundary}")
    html_part.set_boundary(f"images-{related_boundary}")


def build_message(
    team_number,
    team_label,
    recipient,
    from_address,
    image_angle,
    event_year,
    parts,
):
    msg = EmailMessage()
    msg["Subject"] = f"3D Model Submission Receipt - Team {team_number}"
    msg["From"] = from_address
    msg["To"] = recipient

    msg.set_content(build_plain_text(team_number, team_label, event_year, parts))
    msg.add_alternative(
        build_html(team_number, team_label, event_year, parts),
        subtype="html",
    )

    html_part = msg.get_payload()[-1]
    attach_images(html_part, parts)
    set_boundaries(
        msg,
        html_part,
        team_number,
        team_label,
        recipient,
        from_address,
        image_angle,
        parts,
    )
    return msg


def write_output(output_path, msg_bytes):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = output_path.with_name(f".{output_path.name}.tmp")
    temp_path.write_bytes(msg_bytes)
    temp_path.replace(output_path)


def main():
    args = parse_args()

    team_dir = args.team_dir.expanduser().resolve()
    if not team_dir.is_dir():
        raise SystemExit(f"Team directory does not exist: {team_dir}")

    team_number, team_label = parse_team_dir_name(team_dir)
    event_year = date.today().year
    recipient = load_recipient(team_dir)
    parts = collect_parts(team_dir, team_number, args.image_angle)

    output_path = args.output
    if output_path is None:
        output_path = team_dir / f"receipt-{team_number}.eml"
    else:
        output_path = output_path.expanduser().resolve()

    msg = build_message(
        team_number,
        team_label,
        recipient,
        args.from_address,
        args.image_angle,
        event_year,
        parts,
    )
    msg_bytes = bytes(msg)

    if output_path.is_file():
        existing_bytes = output_path.read_bytes()
        if existing_bytes == msg_bytes and not args.force:
            print(f"skip\t{output_path}\tunchanged")
            return

    if args.dry_run:
        print(f"would_write\t{output_path}")
        return

    write_output(output_path, msg_bytes)
    print(f"wrote\t{output_path}")


if __name__ == "__main__":
    main()
