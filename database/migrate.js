
const { Pool } = require('pg');
const fs = require('fs');
const path = require('path');

const pool = new Pool({
  connectionString: process.env.DATABASE_URL
});

async function runMigrations() {
  const client = await pool.connect();
  try {
    await client.query('BEGIN');
    
    // Create migrations table if not exists
    await client.query(`
      CREATE TABLE IF NOT EXISTS migrations (
        id SERIAL PRIMARY KEY,
        name VARCHAR(255) NOT NULL,
        applied_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
      )
    `);

    // Get applied migrations
    const { rows } = await client.query('SELECT name FROM migrations');
    const appliedMigrations = new Set(rows.map(r => r.name));

    // Read migration files
    const migrationFiles = fs.readdirSync(path.join(__dirname, 'migrations'))
      .filter(f => !appliedMigrations.has(f));

    // Apply new migrations
    for (const file of migrationFiles) {
      const sql = fs.readFileSync(path.join(__dirname, 'migrations', file), 'utf8');
      await client.query(sql);
      await client.query('INSERT INTO migrations (name) VALUES ($1)', [file]);
    }

    await client.query('COMMIT');
  } catch (e) {
    await client.query('ROLLBACK');
    throw e;
  } finally {
    client.release();
  }
}

runMigrations().catch(console.error);
