import argparse
import difflib
import tempfile
import yaml
from pathlib import Path

import git
import setuptools_scm


def get_latest_git_rev(git_url: str, branch_name: str):
    """Get latest revision of a branch on a remote Git repository."""
    git_cmd = git.cmd.Git()
    ls_remote_result = git_cmd.ls_remote(git_url, branch_name)
    rev, commit_id = ls_remote_result.split()
    return rev


def replace_context(recipe_str, new_context_line):
    """Replace context line in recipe_str."""
    variable, value = new_context_line.strip().split(": ")
    lines = recipe_str.splitlines()
    for i, line in enumerate(lines):
        if line.strip().startswith(f"{variable}:"):
            # Keep the leading whitespace
            whitespace = line[: line.index(f"{variable}:")]
            lines[i] = f"{whitespace}{new_context_line}"
            break
    return "\n".join(lines)


def update_recipe(recipe_path):
    """Update version and hash in recipe file."""
    print(f"Checking package {recipe_path.parent.name} for updates")

    with open(recipe_path) as f:
        recipe = yaml.safe_load(f)

    try:
        git_url = recipe["context"]["git_url"]
        current_git_rev = recipe["context"]["git_rev"]
    except KeyError:
        print("Recipe does not use `git_url` or `git_rev`, skipping")
        return
    git_branch = recipe["context"].get("git_branch", "HEAD")
    current_base_version = recipe["context"].get("base_version", None)
    current_date_str = recipe["context"].get("date_str", None)
    current_build = recipe["context"].get("build", None)

    latest_git_rev = get_latest_git_rev(git_url, git_branch)

    if latest_git_rev == current_git_rev:
        return

    # rev has changed, clone to temporary directory to get more information
    with tempfile.TemporaryDirectory(suffix=".git") as tempdir:
        repo = git.Repo.clone_from(git_url, tempdir, branch=git_branch, bare=True)
        latest_date_str = repo.head.commit.committed_datetime.strftime("%Y%m%d")
        try:
            latest_prior_tag = repo.git.describe(latest_git_rev, tags=True, abbrev=0)
        except git.GitCommandError:
            latest_base_version = "0.0.0"
        else:
            config = setuptools_scm.Configuration()
            parsed_version = setuptools_scm.version.tag_to_version(
                latest_prior_tag, config
            )
            latest_base_version = str(parsed_version)

    # Update recipe as a string replace because we want to keep all YAML formatting
    orig_recipe_str = recipe_path.read_text()
    recipe_str = replace_context(orig_recipe_str, f"git_rev: {latest_git_rev}")
    recipe_str = replace_context(recipe_str, f'date_str: "{latest_date_str}"')
    recipe_str = replace_context(recipe_str, f'base_version: "{latest_base_version}"')
    if (current_base_version == latest_base_version) and (
        current_date_str == latest_date_str
    ):
        # if base_version and date_str didn't change but rev did, increment build
        recipe_str = replace_context(recipe_str, f'build: "{int(current_build) + 1}"')
    else:
        # reset build to 0
        recipe_str = replace_context(recipe_str, 'build: "0"')
    # restore trailing newline if it was there before
    if orig_recipe_str.endswith("\n"):
        recipe_str += "\n"

    # Save updated recipe
    recipe_path.write_text(recipe_str)

    # Get diff to return for printing
    name = f"{recipe_path.parent.name}/{recipe_path.name}"
    diff_lines = difflib.unified_diff(
        orig_recipe_str.splitlines(),
        recipe_str.splitlines(),
        fromfile=f"{name}.orig",
        tofile=name,
        n=0,
        lineterm="",
    )
    diff = "\n".join(diff_lines)

    print(f"Updated {recipe_path}")
    return diff


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "recipe_dir",
        nargs="?",
        default=Path("recipes"),
        type=Path,
    )
    parser.add_argument(
        "--summary-output",
        dest="summary_output",
        type=Path,
    )
    args = parser.parse_args()

    recipe_dir = args.recipe_dir.resolve()

    diffs = []
    for recipe_path in recipe_dir.glob("**/recipe.yaml"):
        try:
            diff = update_recipe(recipe_path)
            if diff is not None:
                diffs.append(diff)
        except Exception as e:
            print(f"Error processing {recipe_path}: {e}")

    if diffs:
        summary_lines = [
            "",
            "Summary of updates",
            "------------------",
        ]
        for diff in diffs:
            summary_lines.append("```diff")
            summary_lines.append(diff)
            summary_lines.append("```")
        summary = "\n".join(summary_lines)
        print(summary)

        if args.summary_output is not None:
            args.summary_output.write_text(summary)


if __name__ == "__main__":
    main()
