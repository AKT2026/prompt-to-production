"""
UC-0A — Complaint Classifier

Deterministic complaint classifier implementing the rules defined in
agents.md and skills.md.
"""

import argparse
import csv
import re


ALLOWED_CATEGORIES = [
    "Pothole",
    "Flooding",
    "Streetlight",
    "Waste",
    "Noise",
    "Road Damage",
    "Heritage Damage",
    "Heat Hazard",
    "Drain Blockage",
    "Other",
]

SEVERITY_KEYWORDS = [
    "injury",
    "child",
    "school",
    "hospital",
    "ambulance",
    "fire",
    "hazard",
    "fell",
    "collapse",
]


# Ordered keyword rules.
# More specific categories are checked before broader categories.
CATEGORY_RULES = {
    "Pothole": [
        r"\bpothole\b",
        r"\bpotholes\b",
    ],
    "Flooding": [
        r"\bflood\b",
        r"\bflooding\b",
        r"\bwaterlogged\b",
        r"\bwaterlogging\b",
        r"\bwater accumulation\b",
    ],
    "Drain Blockage": [
        r"\bdrain\b",
        r"\bdrainage\b",
        r"\bblocked drain\b",
        r"\bclogged drain\b",
        r"\bsewer\b",
    ],
    "Streetlight": [
        r"\bstreet ?light\b",
        r"\bstreetlights?\b",
        r"\blamp ?post\b",
        r"\blamp post\b",
        r"\blight pole\b",
    ],
    "Waste": [
        r"\bgarbage\b",
        r"\bwaste\b",
        r"\btrash\b",
        r"\brubbish\b",
        r"\bdumping\b",
        r"\bdumped\b",
        r"\bbin\b",
        r"\bgarbage collection\b",
    ],
    "Noise": [
        r"\bnoise\b",
        r"\bloud\b",
        r"\bloudspeaker\b",
        r"\bsound\b",
        r"\bmusic\b",
    ],
    "Heritage Damage": [
        r"\bheritage\b",
        r"\bmonument\b",
        r"\bhistoric\b",
        r"\bhistorical\b",
        r"\bprotected structure\b",
    ],
    "Heat Hazard": [
        r"\bheat\b",
        r"\bheatwave\b",
        r"\bheat wave\b",
        r"\bextreme temperature\b",
        r"\bhot weather\b",
    ],
    "Road Damage": [
        r"\broad damage\b",
        r"\bdamaged road\b",
        r"\bdamaged roads\b",
        r"\broad surface\b",
        r"\bcracked road\b",
        r"\broad crack\b",
        r"\broad\b.*\bdamage\b",
    ],
}


def _find_matches(description: str):
    """
    Return matching categories and the first source phrase found for each.
    """
    matches = {}

    for category, patterns in CATEGORY_RULES.items():
        for pattern in patterns:
            match = re.search(pattern, description, flags=re.IGNORECASE)
            if match:
                matches[category] = match.group(0)
                break

    return matches


def _contains_severity_keyword(description: str):
    """
    Return the first severity keyword found in the description.
    """
    for keyword in SEVERITY_KEYWORDS:
        if re.search(
            rf"\b{re.escape(keyword)}\b",
            description,
            flags=re.IGNORECASE,
        ):
            return keyword

    return None


def classify_complaint(row: dict) -> dict:
    """
    Classify one complaint.

    Returns:
        dict with keys:
        complaint_id, category, priority, reason, flag
    """

    complaint_id = str(row.get("complaint_id", "")).strip()
    description = str(row.get("description", "")).strip()

    # Missing or invalid description.
    if not description:
        return {
            "complaint_id": complaint_id,
            "category": "Other",
            "priority": "Standard",
            "reason": "The complaint description is unavailable.",
            "flag": "NEEDS_REVIEW",
        }

    matches = _find_matches(description)
    severity_keyword = _contains_severity_keyword(description)

    # Multiple category matches mean the description may genuinely
    # describe more than one permitted category.
    if len(matches) > 1:
        matched_categories = ", ".join(matches.keys())
        reason = (
            f'The description contains indicators for {matched_categories}, '
            f'including "{next(iter(matches.values()))}".'
        )

        return {
            "complaint_id": complaint_id,
            "category": "Other",
            "priority": "Urgent" if severity_keyword else "Standard",
            "reason": reason,
            "flag": "NEEDS_REVIEW",
        }

    # Exactly one category match.
    if len(matches) == 1:
        category, matched_phrase = next(iter(matches.items()))

        if severity_keyword:
            reason = (
                f'The description mentions "{matched_phrase}" and '
                f'"{severity_keyword}", so the complaint is classified as '
                f"{category} with Urgent priority."
            )
            priority = "Urgent"
        else:
            reason = (
                f'The description mentions "{matched_phrase}", so the '
                f"complaint is classified as {category}."
            )
            priority = "Standard"

        return {
            "complaint_id": complaint_id,
            "category": category,
            "priority": priority,
            "reason": reason,
            "flag": "",
        }

    # No recognised category.
    reason = (
        f'The description "{description}" does not provide enough '
        "information to determine a permitted category."
    )

    return {
        "complaint_id": complaint_id,
        "category": "Other",
        "priority": "Urgent" if severity_keyword else "Standard",
        "reason": reason,
        "flag": "NEEDS_REVIEW",
    }


def batch_classify(input_path: str, output_path: str):
    """
    Read input CSV, classify every row, and write the results CSV.

    Rows are processed independently so a malformed row does not terminate
    the entire batch.
    """

    output_fields = [
        "complaint_id",
        "category",
        "priority",
        "reason",
        "flag",
    ]

    with open(
        input_path,
        "r",
        newline="",
        encoding="utf-8-sig",
    ) as input_file:

        reader = csv.DictReader(input_file)

        if reader.fieldnames is None:
            raise ValueError("Input CSV has no header row.")

        required_fields = {"complaint_id", "description"}
        missing_fields = required_fields - set(reader.fieldnames)

        if missing_fields:
            raise ValueError(
                f"Input CSV is missing required columns: "
                f"{', '.join(sorted(missing_fields))}"
            )

        results = []

        for row_number, row in enumerate(reader, start=2):
            try:
                result = classify_complaint(row)

            except Exception as exc:
                # Keep the batch running even if one row is malformed.
                result = {
                    "complaint_id": str(
                        row.get("complaint_id", f"ROW-{row_number}")
                    ).strip(),
                    "category": "Other",
                    "priority": "Standard",
                    "reason": (
                        f"Unable to classify this row because of input "
                        f"error: {exc}."
                    ),
                    "flag": "NEEDS_REVIEW",
                }

            # Final validation before writing.
            if result["category"] not in ALLOWED_CATEGORIES:
                result["category"] = "Other"
                result["flag"] = "NEEDS_REVIEW"

            if result["priority"] not in {"Urgent", "Standard", "Low"}:
                result["priority"] = "Standard"
                result["flag"] = "NEEDS_REVIEW"

            results.append(result)

    with open(
        output_path,
        "w",
        newline="",
        encoding="utf-8",
    ) as output_file:

        writer = csv.DictWriter(
            output_file,
            fieldnames=output_fields,
        )

        writer.writeheader()
        writer.writerows(results)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="UC-0A Complaint Classifier"
    )

    parser.add_argument(
        "--input",
        required=True,
        help="Path to test_[city].csv",
    )

    parser.add_argument(
        "--output",
        required=True,
        help="Path to write results CSV",
    )

    args = parser.parse_args()

    batch_classify(args.input, args.output)

    print(f"Done. Results written to {args.output}")
