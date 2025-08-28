import sys
import os
import json
import subprocess
import time
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QTableWidget, QTableWidgetItem,
    QPushButton, QVBoxLayout, QWidget, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QAbstractItemView
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QKeySequence, QShortcut
from database_showcase import Database 


class JobHelperApp(QMainWindow):
    def __init__(self, db):
        super().__init__()
        self.db = db 
        self.scraper_process = None
        self.scraper_timer = QTimer()
        self.scraper_timer.timeout.connect(self.check_scraper_status)
        
        # File paths for subprocess communication
        self.status_file = "scraper_status.json"
        self.jobs_file = "scraped_jobs.jsonl"
        self.stop_file = "scraper_stop.flag"
        self.processed_lines = 0 
        
        self.db_config = {
            'host': 'host',
            'dbname': 'dbname',
            'user': 'user',
            'password': 'password'
        }
        self.setWindowTitle("Job Hunt Assistant")
        self.setGeometry(100, 100, 900, 600)
        self.setup_ui()
        self.load_jobs() 

    def setup_ui(self):
        # Main container
        container = QWidget()
        self.setCentralWidget(container)
        layout = QVBoxLayout()
        container.setLayout(layout)

        # Filters / Input
        filter_layout = QHBoxLayout()
        self.hours_input = QLineEdit()
        self.hours_input.setPlaceholderText("Hours ago...")
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search keyword...")
        self.scrape_button = QPushButton("Scrape Now")
        self.scrape_button.clicked.connect(self.toggle_scraper)
        self.hide_applied_button = QPushButton("Hide Applied")
        self.hide_applied_button.setCheckable(True)
        self.hide_applied_button.clicked.connect(lambda: self.hide_functionality("Applied", self.hide_applied_button))
        self.hide_seen_button = QPushButton("Hide Seen")
        self.hide_seen_button.setCheckable(True)
        self.hide_seen_button.clicked.connect(lambda: self.hide_functionality("Seen", self.hide_seen_button))
        
        # Add refresh button and status label
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self.load_jobs)
        self.status_label = QLabel("Ready")

        filter_layout.addWidget(QLabel("Hours:"))
        filter_layout.addWidget(self.hours_input)
        filter_layout.addWidget(QLabel("Search:"))
        filter_layout.addWidget(self.search_input)
        filter_layout.addWidget(self.scrape_button)
        filter_layout.addWidget(self.refresh_button)
        filter_layout.addWidget(self.hide_applied_button)
        filter_layout.addWidget(self.hide_seen_button)
        filter_layout.addWidget(self.status_label)
        layout.addLayout(filter_layout)

        # Job table
        self.table = QTableWidget()
        self.table.setColumnCount(11)
        self.table.setHorizontalHeaderLabels([
            "ID", "Title", "Company", "Company Location", "Time", "Link", "Type", 
            "Description Upper", "Description Lower", "Status", "is_new"
        ])
        self.table.setColumnHidden(0, True)  # hide the ID column
        self.table.setColumnHidden(10, True) # hide the is_new column
        self.table.verticalHeader().setDefaultSectionSize(60) 
        self.table.cellDoubleClicked.connect(self.show_full_description) # Show full description on double-click
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers) # Make table read-only
        layout.addWidget(self.table)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems) # Select individual cells  
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection) # Allow multi-cell selection
        copy_shortcut = QShortcut(QKeySequence("Ctrl+C"), self.table) # Ctrl+C to copy
        copy_shortcut.activated.connect(self.copy_selection_to_clipboard) # Copy selected cells to clipboard

        # Action buttons
        button_layout = QHBoxLayout()
        self.mark_seen_button = QPushButton("Mark Seen")
        self.mark_seen_button.clicked.connect(lambda: self.update_status("Seen"))
        self.mark_applied_button = QPushButton("Mark Applied")
        self.mark_applied_button.clicked.connect(lambda: self.update_status("Applied"))

        button_layout.addWidget(self.mark_seen_button)
        button_layout.addWidget(self.mark_applied_button)
        layout.addLayout(button_layout)

    # Hide/show functionality for Applied/Seen jobs
    def hide_functionality(self, object, button):
        hide_rows = button.isChecked()

        for row in range(self.table.rowCount()):
            status_item = self.table.item(row, 9)

            if status_item and status_item.text() == object:
                if hide_rows:
                    button.setText(f"Show {object}")
                    self.table.hideRow(row)
                else:
                    button.setText(f"Hide {object}")
                    self.table.showRow(row)

    # Show full description in a message box on double-click                    
    def show_full_description(self, row, column):
        # Description Upper = col 7, Description Lower = col 8
        if column in (7, 8):
            text = self.table.item(row, column).text()
            QMessageBox.information(self, "Full Description", text)

    # Load jobs from DB and populate the table
    def load_jobs(self, limit=50):
        try:
            jobs = self.db.get_jobs(limit=limit)
            self.table.setRowCount(len(jobs))
            print(f"Loading {len(jobs)} jobs into table")

            for row_idx, job in enumerate(jobs):

                # ID (hidden)
                self.table.setItem(row_idx, 0, QTableWidgetItem(str(job["id"])))

                # Title
                title_item = QTableWidgetItem(job["title"] or "")
                title_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(row_idx, 1, title_item)

                # Company
                company_item = QTableWidgetItem(job["company_name"] or "")
                company_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(row_idx, 2, company_item)

                # Company Location
                location_item = QTableWidgetItem(job["company_location"] or "")
                location_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(row_idx, 3, location_item)

                # Time Posted
                time_item = QTableWidgetItem(str(job["time_posted"]) if job["time_posted"] else "")
                time_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(row_idx, 4, time_item)

                # Link
                link_item = QTableWidgetItem(job["link"] or "")
                link_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(row_idx, 5, link_item)

                # Type
                type_item = QTableWidgetItem(job["type"] or "")
                type_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(row_idx, 6, type_item)

                # Description Upper
                desc_upper = job["description_upper"] or ""
                desc_upper_item = QTableWidgetItem(desc_upper)
                desc_upper_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
                desc_upper_item.setToolTip(desc_upper)
                self.table.setItem(row_idx, 7, desc_upper_item)

                # Description Lower
                desc_lower = job["description_lower"] or ""
                desc_lower_item = QTableWidgetItem(desc_lower)
                desc_lower_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
                desc_lower_item.setToolTip(desc_lower)
                self.table.setItem(row_idx, 8, desc_lower_item)

                # Status
                status_item = QTableWidgetItem(job["status"] or "")
                status_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(row_idx, 9, status_item)

                # is_new (hidden)
                item = QTableWidgetItem("")
                item.setData(Qt.ItemDataRole.UserRole, job["is_new"])
                self.table.setItem(row_idx, 10, item)

                if job["is_new"]:
                    self.table.showRow(row_idx)

            self.table.setWordWrap(True)
            self.table.resizeColumnToContents(3)
            self.table.setColumnWidth(7, 250)  # Description Upper
            self.table.setColumnWidth(8, 250)  # Description Lower
            
        except Exception as e:
            print(f"Error loading jobs: {e}")
            QMessageBox.warning(self, "Error", f"Failed to load jobs: {e}")

    # Update job status in DB and table
    def update_status(self, status):
        selected_row = self.table.currentRow()
        if selected_row >= 0:
            try:
                job_id = int(self.table.item(selected_row, 0).text())  # hidden ID column
                self.db.update_job_status(job_id, status) # update DB
                self.db.mark_job_seen(job_id) # mark as seen
                self.table.setItem(selected_row, 9, QTableWidgetItem(status))  # update table
                self.load_jobs()  # refresh table
                print(f"Job {job_id} marked as {status}")
            except Exception as e:
                print(f"Error updating job status: {e}")
                QMessageBox.warning(self, "Error", f"Failed to update job status: {e}")

    # Toggle scraper process on/off                
    def toggle_scraper(self):
        if self.scraper_process and self.scraper_process.poll() is None:
            # Scraper is running, stop it
            self.stop_scraper()
        else:
            # Start scraper
            self.start_scraper()

    # Start the scraper subprocess             
    def start_scraper(self):
        try:
            # Clean up any existing communication files
            for file_path in [self.status_file, self.jobs_file, self.stop_file]:
                if os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                    except:
                        pass
            
            self.processed_lines = 0
            
            # Start the standalone scraper process
            script_path = "standalone_scraper_showcase.py"
            if not os.path.exists(script_path):
                QMessageBox.warning(self, "Error", f"Scraper script not found: {script_path}")
                return
            
            self.scraper_process = subprocess.Popen(
                [sys.executable, script_path],
                cwd=os.getcwd(),
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0
            )
            
            # Start monitoring the scraper
            self.scraper_timer.start(2000) 
            self.scrape_button.setText("Stop Scraping")
            self.status_label.setText("Starting scraper...")
            
            print(f"Started scraper subprocess with PID: {self.scraper_process.pid}")
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to start scraper: {e}")
            print(f"Error starting scraper: {e}")

    # Stop the scraper subprocess gracefully           
    def stop_scraper(self):
        try:
            # Create stop flag file
            with open(self.stop_file, 'w') as f:
                f.write("stop")
            
            self.status_label.setText("Stopping scraper...")
            print("Stop flag created, waiting for scraper to stop...")
            
            # Give it time to stop gracefully
            if self.scraper_process:
                try:
                    self.scraper_process.wait(timeout=12)
                except subprocess.TimeoutExpired:
                    print("Scraper didn't stop gracefully, terminating...")
                    self.scraper_process.terminate()
                    try:
                        self.scraper_process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        print("Force killing scraper process...")
                        self.scraper_process.kill()
            
        except Exception as e:
            print(f"Error stopping scraper: {e}")
        finally:
            self.scraper_cleanup()

    # Cleanup after scraper stops
    def scraper_cleanup(self):
        self.scraper_timer.stop()
        self.scrape_button.setText("Scrape Now")
        self.status_label.setText("Ready")
        self.scraper_process = None
        
        # Clean up communication files
        for file_path in [self.stop_file]:
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except:
                    pass
        
        # Final load of jobs
        self.load_jobs()
        print("Scraper cleanup complete")

    # Check scraper status and process new job data
    def check_scraper_status(self):
        # Check if process is still running
        if self.scraper_process and self.scraper_process.poll() is not None:
            # Process has ended
            print("Scraper process has ended")
            self.scraper_cleanup()
            return
        
        # Read and display status
        try:
            if os.path.exists(self.status_file):
                with open(self.status_file, 'r', encoding='utf-8') as f:
                    status_data = json.load(f)
                
                status = status_data.get('status', 'unknown')
                message = status_data.get('message', '')
                jobs_scraped = status_data.get('jobs_scraped', 0)
                current_page = status_data.get('current_page', 1)
                
                # Update UI
                if status == 'running':
                    self.status_label.setText(f"Scraping page {current_page} ({jobs_scraped} jobs found)")
                elif status == 'completed':
                    self.status_label.setText(f"Completed: {jobs_scraped} jobs scraped")
                    self.scraper_cleanup()
                    return
                elif status == 'stopped':
                    self.status_label.setText(f"Stopped: {jobs_scraped} jobs scraped")
                    self.scraper_cleanup()
                    return
                elif status == 'error':
                    self.status_label.setText(f"Error: {message}")
                    self.scraper_cleanup()
                    return
                else:
                    self.status_label.setText(f"Status: {status}")
        
        except Exception as e:
            print(f"Error reading status file: {e}")
        
        # Process new job data
        self.process_new_jobs()

    # Process new jobs from the JSONL file
    def process_new_jobs(self):
        if not os.path.exists(self.jobs_file):
            return
        
        try:
            jobs_processed = 0
            with open(self.jobs_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            # Process only new lines
            new_lines = lines[self.processed_lines:]
            
            for line in new_lines:
                line = line.strip()
                if not line:
                    continue
                
                try:
                    job_data = json.loads(line)
                    
                    # Insert into database
                    try:
                        self.db.insert_job_to_db(job_data)
                        jobs_processed += 1
                        print(f"Successfully inserted: {job_data.get('Title', 'Unknown')}")
                    except Exception as e:
                        print(f"Error inserting job to DB: {type(e).__name__}: {str(e)}")
                        print(f"Job data that failed: {job_data}")
                        
                except json.JSONDecodeError as e:
                    print(f"Error parsing job data: {e}")
                    continue
            
            # Update processed line count
            self.processed_lines = len(lines)
            
            # Refresh table if we processed any jobs
            if jobs_processed > 0:
                print(f"Processed {jobs_processed} new jobs, refreshing table...")
                self.load_jobs()
                
        except Exception as e:
            print(f"Error processing job data: {e}")

    # Ensure scraper is stopped and DB is closed on app exit
    def closeEvent(self, event):
        if self.scraper_process and self.scraper_process.poll() is None:
            print("Application closing, stopping scraper...")
            self.stop_scraper()
            
            # Give it a moment to stop
            if self.scraper_process:
                try:
                    self.scraper_process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    print("Force killing scraper on app close...")
                    self.scraper_process.kill()
        
        # Close database connection
        if hasattr(self, 'db'):
            try:
                self.db.close()
                print("Database connection closed")
            except Exception as e:
                print(f"Error closing database: {e}")
        
        event.accept()

    # Copy selected table cells to clipboard in tab-separated format
    def copy_selection_to_clipboard(self):
        selection = self.table.selectedRanges()
        if not selection:
            return

        clipboard_text = ""
        for selected_range in selection:
            for row in range(selected_range.topRow(), selected_range.bottomRow() + 1):
                row_data = []
                for col in range(selected_range.leftColumn(), selected_range.rightColumn() + 1):
                    item = self.table.item(row, col)
                    if item:
                        row_data.append(item.text())
                    else:
                        row_data.append("")
                clipboard_text += "\t".join(row_data) + "\n"

        QApplication.clipboard().setText(clipboard_text.strip())
        print("Copied selection to clipboard.")

        
# ---------------------------
# Main
# ---------------------------
if __name__ == "__main__":
    try:
        db = Database(host="host", dbname="dbname", user="user", password="password")
        app = QApplication(sys.argv)
        window = JobHelperApp(db)
        window.show()
        sys.exit(app.exec())
    except Exception as e:
        print(f"Failed to start application: {e}")
        sys.exit(1)
