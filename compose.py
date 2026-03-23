import argparse
import mimetypes
from email.message import EmailMessage
from email.utils import make_msgid
from pathlib import Path


DEFAULT_FROM = "twells@kipr.org"
DEFAULT_IMAGE_ANGLE = 270


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
    return parser.parse_args()


def parse_team_dir_name(team_dir):
    team_name = team_dir.name
    if "-" not in team_name:
        raise SystemExit(
            f"Team directory must be named like <team number>-<team name>: {team_dir}"
        )
    team_number, team_label = team_name.split("-", 1)
    return team_number, team_label


def load_recipient(team_dir):
    email_path = team_dir / "email.txt"
    if not email_path.is_file():
        raise SystemExit(f"Missing email.txt in {team_dir}")

    recipient = email_path.read_text(encoding="utf-8").strip()
    if not recipient:
        raise SystemExit(f"email.txt is empty in {team_dir}")
    return recipient


def collect_parts(team_dir, image_angle):
    stl_files = sorted(team_dir.glob("*.stl"))
    if not stl_files:
        raise SystemExit(f"No STL files found in {team_dir}")

    parts = []
    for stl_path in stl_files:
        image_path = team_dir / stl_path.stem / f"{image_angle}.png"
        if not image_path.is_file():
            raise SystemExit(f"Missing rendered image for {stl_path.name}: {image_path}")
        parts.append(
            {
                "name": stl_path.stem,
                "display_name": stl_path.stem.replace("_", " "),
                "image_path": image_path,
                "cid": make_msgid(domain="local")[1:-1],
            }
        )
    return parts


def build_plain_text(team_number, team_label, parts):
    count = len(parts)
    noun = "part" if count == 1 else "parts"
    lines = [
        f"Team {team_number} ({team_label}),",
        "",
        (
            f"Thank you for your submission. This email certifies that you may use "
            f"the {count} {noun} pictured below."
        ),
        "",
        "Approved parts:",
    ]
    lines.extend(f"- {part['display_name']}" for part in parts)
    return "\n".join(lines)


def build_html(team_number, team_label, parts):
    count = len(parts)
    noun = "part" if count == 1 else "parts"

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

    return (
        f"<p>Team {team_number} ({team_label}),</p>"
        f"<p>Thank you for your submission. This email certifies that you may use the "
        f"<b>{count}</b> {noun} pictured below.</p>"
        f"{''.join(blocks)}"
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


def main():
    args = parse_args()

    team_dir = args.team_dir.expanduser().resolve()
    if not team_dir.is_dir():
        raise SystemExit(f"Team directory does not exist: {team_dir}")

    team_number, team_label = parse_team_dir_name(team_dir)
    recipient = load_recipient(team_dir)
    parts = collect_parts(team_dir, args.image_angle)

    msg = EmailMessage()
    msg["Subject"] = f"3D Model Submission Receipt - Team {team_number}"
    msg["From"] = args.from_address
    msg["To"] = recipient

    msg.set_content(build_plain_text(team_number, team_label, parts))
    msg.add_alternative(build_html(team_number, team_label, parts), subtype="html")

    html_part = msg.get_payload()[-1]
    attach_images(html_part, parts)

    output_path = args.output
    if output_path is None:
        output_path = team_dir / f"receipt-{team_number}.eml"
    else:
        output_path = output_path.expanduser().resolve()

    output_path.write_bytes(bytes(msg))
    print(output_path)


if __name__ == "__main__":
    main()
