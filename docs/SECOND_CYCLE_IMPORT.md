# Importing the second production cycle workbook

Batch numbers restart in every production cycle (cycle 2 has its own Batch 1-6) and animal tags continue as B01, B02 ...

1. `alembic upgrade head` (migration 0040 makes batch numbers unique per cycle; nothing existing is changed).
2. Create the cycle: `POST /api/v1/production-cycles {"name": "2nd Production Cycle", "status": "running"}`; note its `id`.
3. Dry run: `POST /api/v1/feedlot/worksheet/import?dry_run=true&production_cycle_id=<id>` with the workbook.
   Expect 6 intake batches, 112 animals, KES 6,738,100 landed cost (from the BULLS ACQUISATION COST sheet).
   Warnings `batch_number_reused` only say cycle 1's batches were left untouched.
4. Real import: the same call with `dry_run=false`. Re-running it changes nothing; a newer copy of the workbook
   appends only the new weigh dates and batches.
5. Check Cycles > summary and Feedlot > performance against the workbook's SUMMARY ADG sheet.

Matching rule: with a cycle selected a sheet only matches the batch with that number inside that cycle. An unassigned
batch with the same number is adopted only if its delivery date is identical; otherwise it is left alone.
