#!/usr/bin/env python3
"""
Remote Music Tagger Runner
Executes music-tagger on NAS via SSH without file transfer
"""

import subprocess
import sys
import argparse

NAS_USER = "ccfadmin"
NAS_HOST = "10.10.1.211"
NAS_PORT = 22
NAS_DIR = "/vol2/1000/openclaw/music-tagger"
NAS_MUSIC = "/vol2/1000/Music/临时"


def run_cmd_on_nas(command: str) -> int:
    """Run a command on NAS via SSH"""
    ssh_cmd = [
        "ssh",
        "-o", "StrictHostKeyChecking=no",
        "-o", "BatchMode=yes",
        "-p", str(NAS_PORT),
        f"{NAS_USER}@{NAS_HOST}",
        command
    ]
    
    result = subprocess.run(ssh_cmd, capture_output=False, text=True)
    return result.returncode


def run_remote(command="run", verbose=False):
    """Run music-tagger remotely on NAS"""
    
    if verbose:
        print(f"[SSH] Executing remote command: {command}")
        print()
    
    cmd = f"cd {NAS_MUSIC} && source {NAS_DIR}/.venv/bin/activate && python3 {NAS_DIR}/music_tagger/cli_ssh.py {command}"
    
    return run_cmd_on_nas(cmd)


def get_status():
    """Get status from NAS"""
    cmd = f"cd {NAS_MUSIC} && source {NAS_DIR}/.venv/bin/activate && python3 {NAS_DIR}/music_tagger/cli_ssh.py status"
    return run_cmd_on_nas(cmd)


def main():
    parser = argparse.ArgumentParser(
        description="Remote Music Tagger - Execute on NAS via SSH (no file transfer)",
        epilog=(
            "Examples:\n"
            "  %(prog)s run              # Execute full pipeline\n"
            "  %(prog)s status           # Check status\n"
            "  %(prog)s -v run           # Verbose output"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument("command", 
                       choices=["run", "scan", "match", "tag", "rename", 
                               "organize", "status", "retry"],
                       help="Command to execute on NAS")
    parser.add_argument("-v", "--verbose", action="store_true",
                       help="Verbose output")
    
    args = parser.parse_args()
    
    if args.command == "status":
        return get_status()
    else:
        return run_remote(args.command, args.verbose)


if __name__ == "__main__":
    sys.exit(main())
