import argparse
import tempfile
import traceback
from pathlib import Path

import copier
import git
import license_expression
import rich.console
import rich.markdown
import yaml


def inspect_git_repo(git_url, git_branch=None):
    """Fetch git repo and inspect it to generate default answers for copier"""
    prefilled_answers = {
        "git_url": git_url,
    }

    # determine OOT name from git url
    repo_name = Path(git_url).stem
    if repo_name.startswith("gr-"):
        prefilled_answers["oot_name"] = repo_name.removeprefix("gr-")
    else:
        prefilled_answers["oot_name"] = repo_name

    clone_kwargs = {}
    if git_branch is not None:
        clone_kwargs["branch"] = git_branch
    with tempfile.TemporaryDirectory(prefix=f"{repo_name}_", suffix=".git") as tmp_dir:
        repo = git.Repo.clone_from(git_url, tmp_dir, **clone_kwargs)

        # get git branch from checked out repo
        git_branch = repo.active_branch.name
        prefilled_answers["git_branch"] = git_branch

        try:
            repo_path = Path(tmp_dir)
            # get info from MANIFEST file, if it exists
            manifest_path = repo_path / "MANIFEST.yml"
            if manifest_path.exists():
                manifest = manifest_path.read_text()
                manifest_dict = yaml.safe_load(manifest)
            else:
                # try old markdown manifest
                manifest_path = repo_path / "MANIFEST.md"
                if manifest_path.exists():
                    manifest = manifest_path.read_text()
                    separator_idx = manifest.find("---")
                    manifest_dict = yaml.safe_load(manifest[:separator_idx])
                    manifest_dict["description"] = manifest[separator_idx + 3 :].strip()
                else:
                    manifest_dict = {}

            # get summary from brief
            brief = manifest_dict.get("brief", "")
            if brief:
                prefilled_answers["summary"] = brief

            # get description
            description = manifest_dict.get("description", "")
            if description:
                prefilled_answers["description"] = description

            # get license
            license = manifest_dict.get("license", "")
            licensing = license_expression.get_spdx_licensing()
            try:
                parsed_license = licensing.parse(license, validate=True)
            except license_expression.ExpressionError:
                pass
            else:
                if parsed_license:
                    prefilled_answers["license"] = str(parsed_license)

        except Exception:
            tb = traceback.format_exc()
            print(f"Error inspecting git repo {git_url}: {tb}")

    # return dict of answers that we've guessed
    return prefilled_answers


def run_copier(src_path, dst_path, prefilled_answers=None, **copier_kwargs):
    """Run copier to create a recipe from the given template and default answers."""
    if prefilled_answers is None:
        prefilled_answers = {}
    answers_path = dst_path / ".copier-answers.yml"

    copier.run_copy(
        src_path=src_path,
        dst_path=dst_path,
        user_defaults=prefilled_answers,
        **copier_kwargs,
    )

    with open(answers_path) as f:
        answers = yaml.safe_load(f)

    return answers


def generate_recipe_from_template(
    git_url,
    output_path=None,
    template_url="https://github.com/radioconda/gnuradio-oot-recipe-template",
    **copier_kwargs,
):
    """Generate an OOT module recipe using a copier template."""
    print(f"Generating recipe for OOT at url: {git_url}")

    prefilled_answers = inspect_git_repo(git_url)
    name = prefilled_answers["oot_name"]

    if output_path is None:
        output_path = Path("recipes").resolve() / f"{name}"

    answers = run_copier(
        src_path=template_url,
        dst_path=output_path,
        prefilled_answers=prefilled_answers,
        **copier_kwargs,
    )

    print(f"Generated recipe for {name} at {output_path}")
    return answers


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "git_url",
        type=str,
        help="URL for OOT module Git repository",
    )
    parser.add_argument(
        "-o",
        "--output-path",
        dest="output_path",
        default=None,
        type=Path,
        help="Output directory for the filled recipe, default: recipes/{{oot_name}}",
    )
    parser.add_argument(
        "--template-url",
        dest="template_url",
        default="https://github.com/radioconda/gnuradio-oot-recipe-template",
        type=str,
        help="URL for recipe template, default: %(default)s",
    )
    parser.add_argument(
        "--summary-output",
        dest="summary_output",
        type=Path,
        help="File to write summary output to",
    )
    parser.add_argument(
        "--defaults",
        action="store_true",
        help=(
            "Flag to use default answers to questions, which might be null if not "
            "specified"
        ),
    )
    parser.add_argument(
        "--data",
        action="append",
        help="Answers to the questionnaire defined in the template",
    )
    parser.add_argument(
        "--data-file",
        dest="data_file",
        type=Path,
        help="YAML file containing answers to the template questionnaire",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Flag to verwrite files that already exist, without asking",
    )
    args = parser.parse_args()

    data = {}
    if args.data is not None:
        for data_arg in args.data:
            key, value = data_arg.split("=", 1)
            data[key] = value

    if args.data_file is not None:
        with args.data_file.open("rb") as f:
            file_updates = yaml.safe_load(f)
        updates_without_cli_overrides = {
            k: v for k, v in file_updates.items() if k not in data
        }
        data.update(updates_without_cli_overrides)

    copier_kwargs = {
        "defaults": args.defaults,
        "overwrite": args.overwrite,
    }
    if data:
        copier_kwargs["data"] = data

    try:
        answers = generate_recipe_from_template(
            args.git_url,
            output_path=args.output_path,
            template_url=args.template_url,
            **copier_kwargs,
        )
    except KeyboardInterrupt:
        return

    summary = ""
    if answers:
        summary_lines = [
            "",
            "Summary of generated recipe",
            "---------------------------",
            "| Template Key | Value |",
            "| ------------ | ----- |",
        ]
        for key, val in answers.items():
            summary_lines.append(f"| **{key}** | {val} |".replace("\n", " " * 4))
        summary = "\n".join(summary_lines)
        md = rich.markdown.Markdown(summary)

        console = rich.console.Console()
        console.print(md)

    if args.summary_output is not None:
        with args.summary_output.open("a") as f:
            f.write(summary)


if __name__ == "__main__":
    main()
