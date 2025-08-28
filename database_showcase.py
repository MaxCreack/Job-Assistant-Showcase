import psycopg2
from psycopg2.extras import RealDictCursor
import traceback

class Database:
    def __init__(self, host, dbname, user, password):
        self.conn = psycopg2.connect(
            host=host,
            dbname=dbname,
            user=user,
            password=password
        )
        self.cur = self.conn.cursor(cursor_factory=RealDictCursor) 

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
                j.description_upper,
                j.description_lower,
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
                WHERE id = %s
            """, (job_id,))
            self.conn.commit()
            print(f"Job {job_id} marked as seen.")
        except Exception as e:
            print(f"Error marking job as seen: {e}")
            self.conn.rollback()
            raise

    def update_job_status(self, job_id, status):
        try:
            self.cur.execute("""
                INSERT INTO user_actions (job_id, status)
                VALUES (%s, %s)
                ON CONFLICT (job_id) DO UPDATE
                SET status = EXCLUDED.status;

                UPDATE jobs
                SET is_new = FALSE
                WHERE id = %s;
            """, (job_id, status, job_id))
            self.conn.commit()
            print(f"Status updated for job {job_id}: {status}")
        except Exception as e:
            print(f"Error updating job status: {e}")
            self.conn.rollback()
            raise

    def insert_job_to_db(self, job_data):
        try:
            print(f"Attempting to insert job: {job_data.get('Title', 'Unknown Title')}")
            
            # Validate required fields
            required_fields = ['Title', 'Company', 'Time', 'Link', 'Location', 'Type', 'Description Upper', 'Description Lower']
            for field in required_fields:
                if field not in job_data:
                    raise ValueError(f"Missing required field: {field}")
            
            # Clean and validate data
            company_name = str(job_data['Company']).strip()[:255] if job_data['Company'] else 'Unknown'
            location = str(job_data['Location']).strip()[:255] if job_data['Location'] else 'Unknown'
            title = str(job_data['Title']).strip()[:500] if job_data['Title'] else 'Unknown'
            link = str(job_data['Link']).strip()[:500] if job_data['Link'] else ''
            job_type = str(job_data['Type']).strip()[:100] if job_data['Type'] else 'Unknown'
            desc_upper = str(job_data['Description Upper']).strip() if job_data['Description Upper'] else ''
            desc_lower = str(job_data['Description Lower']).strip() if job_data['Description Lower'] else ''
            
            if not company_name or company_name == 'Unknown':
                raise ValueError("Company name cannot be empty")
            
            # Insert company if it doesn't exist
            print(f"Inserting/finding company: {company_name}")
            self.cur.execute("""
                INSERT INTO companies (name, location)
                VALUES (%s, %s)
                ON CONFLICT (name) DO NOTHING
                RETURNING id
            """, (company_name, location))
        
            result = self.cur.fetchone()
            if result is None:
                # Company already exists, get its ID
                self.cur.execute("SELECT id FROM companies WHERE name = %s", (company_name,))
                result = self.cur.fetchone()
                if result is None:
                    raise ValueError(f"Could not find or create company: {company_name}")
                company_id = result['id']
            else:
                company_id = result['id']
            
            print(f"Company ID: {company_id}")

            # Insert job with duplicate-safe logic
            print("Inserting job...")
            self.cur.execute("""
                INSERT INTO jobs (title, company_id, time_posted, link, type, description_upper, description_lower)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (title, company_id) DO NOTHING
            """, (
                title,
                company_id,
                job_data['Time'],
                link,
                job_type,
                desc_upper,
                desc_lower
            ))

            # Check if the job was actually inserted
            if self.cur.rowcount == 0:
                print(f"Job already exists (duplicate): {title}")
            else:
                print(f"Successfully inserted new job: {title}")
            self.conn.commit()
            
        except Exception as e:
            print(f"Database insertion failed: {type(e).__name__}: {str(e)}")
            print(f"Job data: {job_data}")
            traceback.print_exc()
            self.conn.rollback()
            raise