"""Opsional: jalankan sql/schema.sql (dan sample data) dari komputer Anda.

    python scripts/init_db.py "postgresql://..."            # skema saja
    python scripts/init_db.py "postgresql://..." --sample   # + data contoh

Alternatif tanpa Python: tempel isi sql/schema.sql ke Supabase SQL Editor lalu Run.
"""
import pathlib
import sys

import psycopg

ROOT = pathlib.Path(__file__).resolve().parent.parent


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    url = sys.argv[1]
    files = [ROOT / "sql" / "schema.sql"]
    if "--sample" in sys.argv:
        files.append(ROOT / "sql" / "sample_data.sql")
    with psycopg.connect(url, autocommit=True) as conn:
        for f in files:
            print(f"Menjalankan {f.name} ...")
            conn.execute(f.read_text(encoding="utf-8"))
    print("Selesai.")


if __name__ == "__main__":
    main()
