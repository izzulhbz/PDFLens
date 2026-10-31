-- Runs once, when the Postgres volume is first initialised (an empty volume).
-- Creates a separate database for the pytest integration tests, so tests can
-- wipe tables freely without touching your development data.
-- The pgvector extension is created in each database by the Alembic migration.
CREATE DATABASE pdflens_test;
