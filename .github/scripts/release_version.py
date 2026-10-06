"""Derive Play version metadata without interpolating tag or input text into shell."""
import os
from pathlib import Path
import re


def release_version(event, ref_type, ref_name, input_name, base, run_number):
    if event == "push" and ref_type == "tag" and ref_name.startswith("v"):
        version_name = ref_name[1:]
    elif event == "workflow_dispatch":
        version_name = input_name
    else:
        raise ValueError("Release requires a v* tag or a manual workflow invocation.")

    if not re.fullmatch(r"\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?", version_name):
        raise ValueError("Version name must look like 0.1.1 or 0.1.1-rc.1.")
    if not re.fullmatch(r"[0-9]+", base) or not re.fullmatch(r"[0-9]+", run_number):
        raise ValueError("ANDROID_VERSION_CODE_BASE and GITHUB_RUN_NUMBER must be integers.")
    version_code = int(base) + int(run_number)
    if int(run_number) < 1 or not 1 <= version_code <= 2100000000:
        raise ValueError("Generated versionCode must be between 1 and 2100000000.")
    return version_name, version_code


def main():
    base = os.environ.get("ANDROID_VERSION_CODE_BASE", "")
    if not base:
        raise ValueError("Set GitHub Variable ANDROID_VERSION_CODE_BASE to the largest versionCode already uploaded to Play.")
    version_name, version_code = release_version(
        os.environ["GITHUB_EVENT_NAME"],
        os.environ["GITHUB_REF_TYPE"],
        os.environ["GITHUB_REF_NAME"],
        os.environ.get("INPUT_VERSION_NAME", ""),
        base,
        os.environ["GITHUB_RUN_NUMBER"],
    )
    with Path(os.environ["GITHUB_OUTPUT"]).open("a") as output:
        output.write(f"version_name={version_name}\nversion_code={version_code}\n")
    print(f"Release {version_name}, versionCode {version_code}")


if __name__ == "__main__":
    main()
