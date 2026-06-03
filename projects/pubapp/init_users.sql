-- Run this AFTER database.sql to add the app_users table
-- Used for JWT authentication

CREATE TABLE IF NOT EXISTS app_users (
  id               SERIAL       PRIMARY KEY,
  username         VARCHAR(100),              -- display name, optional, NOT unique
  email            VARCHAR(320) NOT NULL UNIQUE,
  hashed_password  VARCHAR(200) NOT NULL,
  role             VARCHAR(20)  NOT NULL DEFAULT 'user' CHECK (role IN ('admin', 'user')),
  is_active        BOOLEAN      NOT NULL DEFAULT TRUE
);

-- Migration note: if upgrading from old schema with username NOT NULL UNIQUE:
-- ALTER TABLE app_users DROP CONSTRAINT IF EXISTS app_users_username_key;
-- ALTER TABLE app_users ALTER COLUMN username DROP NOT NULL;
