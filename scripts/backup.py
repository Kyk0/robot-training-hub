"""Consistent SQLite online backup. Source/artifact trees must also be backed up."""

import argparse
import sqlite3
from hub.config import Config

p = argparse.ArgumentParser()
p.add_argument("destination")
a = p.parse_args()
with sqlite3.connect(Config().db) as source, sqlite3.connect(a.destination) as target:
    source.backup(target)
print(
    "Database backup complete. Retain matching data/snapshots and data/runs directories."
)
