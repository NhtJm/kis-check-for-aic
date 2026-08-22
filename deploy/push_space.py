#!/usr/bin/env python3
"""Dua ban nay len Hugging Face Spaces.

    huggingface-cli login          # lam mot lan, can token cua ban
    python3 deploy/push_space.py <user>/<space-name> [--private]

Script tu tao Space neu chua co, roi day dung nhung file can thiet.
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

import argparse, os, shutil, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Chi day nhung file Space thuc su can. videos/, media-info/, .env deu khong len.
import glob as _glob
_R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Lay ca thu muc src/ va web/ thay vi liet ke tung file -- liet ke tay da tung
# bo sot team.py roi bo sot ca 5 trang quan tri.
FILES = ([os.path.relpath(p, _R) for p in _glob.glob(os.path.join(_R, "src", "*.py"))]
         + [os.path.relpath(p, _R) for p in _glob.glob(os.path.join(_R, "web", "*"))]
         + ["requirements.txt", "requirements-local.txt"])
RENAME = {"deploy/Dockerfile.spaces": "Dockerfile",
          "deploy/README-spaces.md": "README.md"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("space", help="vd NhtJm/kis-check-for-aic")
    ap.add_argument("--private", action="store_true")
    a = ap.parse_args()

    from huggingface_hub import HfApi
    api = HfApi()
    try:
        who = api.whoami()["name"]
    except Exception:
        sys.exit("Chua dang nhap. Chay:  huggingface-cli login")
    print(f"dang nhap voi: {who}")

    missing = [f for f in FILES + list(RENAME) if not os.path.exists(os.path.join(ROOT, f))]
    if missing:
        sys.exit("Thieu file: " + ", ".join(missing) + "\n(chay build_viewer.py truoc?)")

    api.create_repo(a.space, repo_type="space", space_sdk="docker",
                    private=a.private, exist_ok=True)
    print(f"Space san sang: https://huggingface.co/spaces/{a.space}"
          + (" (private)" if a.private else " (public)"))

    tmp = tempfile.mkdtemp()
    try:
        for f in FILES:
            dst = os.path.join(tmp, f)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy(os.path.join(ROOT, f), dst)
        for src, dst in RENAME.items():
            shutil.copy(os.path.join(ROOT, src), os.path.join(tmp, dst))
        total = sum(os.path.getsize(os.path.join(tmp, f)) for f in os.listdir(tmp))
        print(f"day {len(os.listdir(tmp))} file ({total/1e6:.1f} MB) ...")
        api.upload_folder(folder_path=tmp, repo_id=a.space, repo_type="space",
                          commit_message="KIS submission checker")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print(f"\nXong: https://huggingface.co/spaces/{a.space}")
    print("Build mat vai phut (cai torch CPU + nap san SigLIP ~1.5GB).")
    print("Xem tien do o tab Logs cua Space.")
    if not a.private:
        print("\nLUU Y: Space public thi ai cung bam cham diem duoc. Chi dat")
        print("KIS_API_KEY o Settings > Secrets neu ban chap nhan nguoi la tieu credit.")


if __name__ == "__main__":
    main()
