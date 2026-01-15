import sqlite3
import traceback
import logging
import sys
from pathlib import Path
from appdirs import user_data_dir

logger = logging.getLogger("job_helper.db")
logger.setLevel(logging.DEBUG)
log_dir = Path("logs")

if not logger.handlers:
    log_file = log_dir / "job_helper_DB.log"
    fh = logging.FileHandler(log_file, encoding='utf-8')
    ch = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    fh.setFormatter(formatter)
    ch.setFormatter(formatter)
    logger.addHandler(fh)
    logger.addHandler(ch)

class Database:
    def __init__(self):
        data_dir = Path(user_data_dir("JobScraper", appauthor=False)) # C:\Users\<USERNAME>\AppData\Local\JobScraper\
        data_dir.mkdir(parents=True, exist_ok=True)

        if getattr(sys, 'frozen', False):
            db_path = data_dir / "jhdb.db"
        else:
            db_path = data_dir / "jhdb_test.db"

        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.cur = self.conn.cursor()

        self.cur.execute("PRAGMA foreign_keys = ON;")

        self.cur.execute("""
        CREATE TABLE IF NOT EXISTS companies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            location TEXT
        );
        """)

        self.cur.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            company_id INTEGER NOT NULL,
            time_posted TEXT,
            link TEXT,
            type TEXT,
            description TEXT,
            is_new BOOLEAN DEFAULT 1,
            FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE CASCADE,
            UNIQUE(title, company_id)
        );
        """)

        self.cur.execute("""
        CREATE TABLE IF NOT EXISTS user_actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER UNIQUE,
            status TEXT,
            timestamp TEXT DEFAULT (DATETIME('now')),
            FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE
        );
        """)

        self.conn.commit()

    def close(self):
        self.cur.close()
        self.conn.close()

    def get_jobs(self, limit=None):
        query = """
            SELECT 
                j.id,
                j.title,
                c.name AS company_name,
                c.location AS company_location,
                j.time_posted,
                j.link,
                j.type,
                j.description,
                ua.status,
                j.is_new
            FROM jobs j
            JOIN companies c ON j.company_id = c.id
            LEFT JOIN user_actions ua ON j.id = ua.job_id
            ORDER BY j.is_new DESC, j.time_posted DESC
            """
        if limit:
            query += f" LIMIT {limit}"
        self.cur.execute(query)
        return self.cur.fetchall()

    def mark_job_seen(self, job_id):
        try:
            self.cur.execute("""
                UPDATE jobs
                SET is_new = FALSE
                WHERE id = ?
            """, (job_id,))
            self.conn.commit()
            logger.info(f"Job {job_id} marked as seen.")
        except Exception as e:
            logger.error(f"Error marking job as seen: {e}")
            self.conn.rollback()
            raise

    def update_job_status(self, job_id, status):
        try:
            self.cur.execute("""
                INSERT INTO user_actions (job_id, status)
                VALUES (?, ?)
                ON CONFLICT(job_id) DO UPDATE SET status = EXCLUDED.status
            """, (job_id, status))

            self.cur.execute("""
                UPDATE jobs
                SET is_new = FALSE
                WHERE id = ?
            """, (job_id,))

            self.conn.commit()
            logger.info(f"Status updated for job {job_id}: {status}")
        except Exception as e:
            logger.error(f"Error updating job status: {e}")
            self.conn.rollback()
            raise

    def insert_job_to_db(self, job_data):
        try:
            logger.info(f"Attempting to insert job: {job_data.get('Title', 'Unknown Title')}")
            
            required_fields = ['Title', 'Company', 'Time', 'Link', 'Location', 'Type', 'Description']
            for field in required_fields:
                if field not in job_data:
                    raise ValueError(f"Missing required field: {field}")
            
            company_name = str(job_data['Company']).strip()[:255] if job_data['Company'] else 'Unknown'
            location = str(job_data['Location']).strip()[:255] if job_data['Location'] else 'Unknown'
            title = str(job_data['Title']).strip()[:500] if job_data['Title'] else 'Unknown'
            link = str(job_data['Link']).strip()[:500] if job_data['Link'] else ''
            job_type = str(job_data['Type']).strip()[:100] if job_data['Type'] else 'Unknown'
            desc = str(job_data['Description']).strip() if job_data['Description'] else ''
            
            if not company_name or company_name == 'Unknown':
                raise ValueError("Company name cannot be empty")
            
            logger.info(f"Inserting/finding company: {company_name}")
            self.cur.execute("""
                INSERT INTO companies (name, location)
                VALUES (?, ?)
                ON CONFLICT (name) DO NOTHING
                RETURNING id
            """, (company_name, location))
        
            result = self.cur.fetchone()
            if result is None:
                self.cur.execute("SELECT id FROM companies WHERE name = ?", (company_name,))
                result = self.cur.fetchone()
                if result is None:
                    raise ValueError(f"Could not find or create company: {company_name}")
                company_id = result['id']
            else:
                company_id = result['id']
            
            logger.info(f"Company ID: {company_id}")

            logger.info("Inserting job...")
            self.cur.execute("""
                INSERT INTO jobs (title, company_id, time_posted, link, type, description)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT (title, company_id) DO NOTHING
            """, (
                title,
                company_id,
                job_data['Time'],
                link,
                job_type,
                desc
            ))

            if self.cur.rowcount == 0:
                logger.warning(f"Job already exists (duplicate): {title}")
            else:
                logger.info(f"Successfully inserted new job: {title}")
            self.conn.commit()
            
        except Exception as e:
            logger.error(f"Database insertion failed: {type(e).__name__}: {str(e)}")
            logger.debug(f"Job data: {job_data}")
            traceback.print_exc()
            self.conn.rollback()
            raise

    def delete_job(self, job_id):
        try:
            self.cur.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
            self.conn.commit()
            logger.info(f"Database: Job {job_id} deleted.")
        except Exception as e:
            logger.error(f"Data deletion failed: {type(e).__name__}: {str(e)}")
            logger.debug(f"Error deleting job: {job_id}")
            self.conn.rollback()
            raise
