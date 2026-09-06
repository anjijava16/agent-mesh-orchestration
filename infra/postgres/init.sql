-- Runs once, on first boot of an empty data volume.
-- Alembic owns the schema; this file only sets up what a migration cannot.

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";   -- trigram search over message content

-- ADK's DatabaseSessionService creates its own tables in this database. Giving
-- it a dedicated schema keeps our migrations from tripping over its DDL.
CREATE SCHEMA IF NOT EXISTS adk;

ALTER DATABASE agentmesh SET timezone TO 'UTC';

-- Separate database for Arize Phoenix (AI observability).
-- Phoenix manages its own schema and migrations.
CREATE DATABASE phoenix;
