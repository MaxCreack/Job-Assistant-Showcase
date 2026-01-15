import sys
import os
import json
import subprocess
import logging
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QTableWidget, QTableWidgetItem,
    QPushButton, QVBoxLayout, QWidget, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QAbstractItemView, QDialog, QComboBox, QTextEdit, QMenu,
    QCheckBox, QMenuBar
)
from PyQt6.QtCore import Qt, QTimer, QSettings
from PyQt6.QtGui import QKeySequence, QShortcut, QIntValidator
from datetime import datetime, timedelta

logger = logging.getLogger("job_helper.app")
logger.setLevel(logging.DEBUG)
log_dir = Path("logs")
log_dir.mkdir(exist_ok=True)

if not logger.handlers:
    log_file = log_dir / "job_helper_app.log"
    fh = logging.FileHandler(log_file, encoding='utf-8')
    ch = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    fh.setFormatter(formatter)
    ch.setFormatter(formatter)
    logger.addHandler(fh)
    logger.addHandler(ch)

from database import Database
from scrapers import list_available_scrapers  


class JobHelperApp(QMainWindow):
    def __init__(self, db):
        super().__init__()
        self.db = db 
        self.settings = QSettings("Baluma", "JobHelperApp")
        self.never_show_delete_warning = self.settings.value("never_show_delete_warning", False, type=bool)
        self.scraper_process = None
        self.scraper_timer = QTimer()
        self.scraper_timer.timeout.connect(self.check_scraper_status)
        self.hide_applied = False
        self.hide_seen = False
        
        self.status_file = "scraper_status.json"
        self.jobs_file = "scraped_jobs.jsonl"
        self.stop_file = "scraper_stop.flag"
        self.excluded_words_file = "excludedwords.json"
        self.exclude_titles, self.exclude_companies = self.load_excluded_words()
        self.processed_lines = 0  
        
        self.setWindowTitle("Software for Job Hunting")
        self.setGeometry(100, 100, 900, 600)
        self.setup_ui()
        self.load_jobs() 

    def setup_ui(self):
        container = QWidget()
        self.setCentralWidget(container)
        layout = QVBoxLayout()
        container.setLayout(layout)

        self.menu = QMenuBar()
        self.fileMenu = self.menu.addMenu("File")
        self.fileMenu.addAction("Reset Preferences", self.reset_preferences)
        self.fileMenu.addAction("Reset Rows and Columns", self.reset_rows_columns)
        self.setMenuBar(self.menu)

        filter_layout = QHBoxLayout()
        
        # Site selection dropdown 
        self.site_dropdown = QComboBox()
        available_scrapers = list_available_scrapers()
        if not available_scrapers:
            logger.warning("No scrapers found! Check scrapers/ folder.")
            available_scrapers = ["No scrapers available"]
        self.site_dropdown.addItems(available_scrapers)
        filter_layout.addWidget(QLabel("Site:"))
        filter_layout.addWidget(self.site_dropdown)
        
        self.hours_input = QLineEdit()
        self.hours_input.setPlaceholderText("Hours ago...")
        self.hours_input.setValidator(QIntValidator(0, 1000))
        self.hours_input.textChanged.connect(self.on_filter_change)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search keyword...")
        self.search_input.textChanged.connect(self.on_filter_change)
        self.scrape_button = QPushButton("Scrape Now")
        self.scrape_button.clicked.connect(self.toggle_scraper)
        self.hide_applied_button = QPushButton("Hide Applied")
        self.hide_applied_button.setCheckable(True)
        self.hide_applied_button.clicked.connect(lambda: self.hide_functionality("Applied", self.hide_applied_button))
        self.hide_seen_button = QPushButton("Hide Seen")
        self.hide_seen_button.setCheckable(True)
        self.hide_seen_button.clicked.connect(lambda: self.hide_functionality("Seen", self.hide_seen_button))
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self.load_jobs)
        self.status_label = QLabel("Ready")
        self.excluded_words_button = QPushButton("Excluded Words")
        self.excluded_words_button.clicked.connect(self.excluded_words)

        filter_layout.addWidget(QLabel("Hours:"))
        filter_layout.addWidget(self.hours_input)
        filter_layout.addWidget(QLabel("Search:"))
        filter_layout.addWidget(self.search_input)
        filter_layout.addWidget(self.scrape_button)
        filter_layout.addWidget(self.excluded_words_button)
        filter_layout.addWidget(self.refresh_button)
        filter_layout.addWidget(self.hide_applied_button)
        filter_layout.addWidget(self.hide_seen_button)
        filter_layout.addWidget(self.status_label)
        layout.addLayout(filter_layout)

        self.table = QTableWidget()
        self.table.setColumnCount(10)
        self.table.setHorizontalHeaderLabels([
            "ID", "Title", "Company", "Job Location", "Time", "Link", "Type", 
            "Description", "Status", "is_new"
        ])
        self.table.setColumnHidden(0, True)
        self.table.setColumnHidden(9, True)
        self.table.verticalHeader().setDefaultSectionSize(60)
        self.table.cellDoubleClicked.connect(self.show_full_description)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)  
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_table_menu)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.setStyleSheet("""
        QTableWidget {
            background-color: #ffffff;
            alternate-background-color: #f5f5f5;
            selection-background-color: #fcfcfc;  
            selection-color: #000000;         
        }
        QTableWidget::item {
            border: 1px solid #d0d0d0;
            padding: 2px;
        }
        QTableWidget::item:selected {
            background-color: white;
            color: black;
            border: 1px solid #000000;
        }
        """)
        layout.addWidget(self.table)
        copy_shortcut = QShortcut(QKeySequence("Ctrl+C"), self.table)
        copy_shortcut.activated.connect(self.copy_selection_to_clipboard)

        button_layout = QHBoxLayout()
        self.mark_seen_button = QPushButton("Mark Seen")
        self.mark_seen_button.clicked.connect(lambda: self.update_status("Seen"))
        self.mark_applied_button = QPushButton("Mark Applied")
        self.mark_applied_button.clicked.connect(lambda: self.update_status("Applied"))
        button_layout.addWidget(self.mark_seen_button)
        button_layout.addWidget(self.mark_applied_button)
        layout.addLayout(button_layout)

    def reset_rows_columns(self):
        """Reset all columns AND rows to default reasonable sizes"""
        self.table.setColumnWidth(1, 200) 
        self.table.setColumnWidth(2, 150) 
        self.table.setColumnWidth(3, 120) 
        self.table.setColumnWidth(4, 130)  
        self.table.setColumnWidth(5, 100) 
        self.table.setColumnWidth(6, 80)    
        self.table.setColumnWidth(7, 250)  
        self.table.setColumnWidth(8, 80)   

        vertical_header = self.table.verticalHeader()
        vertical_header.setDefaultSectionSize(60)
        for row in range(self.table.rowCount()):
            self.table.setRowHeight(row, 60)

        logger.info("Column widths and row heights reset to defaults")

    def load_jobs_with_filters(self, limit=50):
        """Reload jobs and reapply current filters"""
        current_hours = self.hours_input.text().strip()
        current_search = self.search_input.text().strip()
        hide_applied_checked = self.hide_applied_button.isChecked()
        hide_seen_checked = self.hide_seen_button.isChecked()
    
        self.load_jobs(limit)
    
        if current_hours or current_search:
            hours_value = None
            if current_hours:
                try:
                    hours_value = int(current_hours)
                except ValueError:
                    pass
            self.filtering_functionality(hours_value, current_search)
    
        if hide_applied_checked:
            self.hide_functionality("Applied", self.hide_applied_button)
        if hide_seen_checked:
            self.hide_functionality("Seen", self.hide_seen_button)

    def reset_preferences(self):
        self.settings.clear()
        self.never_show_delete_warning = False
        QMessageBox.information(self, "Reset Successful", "Preferences have been reset successfully!")
        logger.info("Preferences reset")

    def show_table_menu(self, pos):
        row = self.table.rowAt(pos.y())
        col = self.table.columnAt(pos.x())
        if row == -1 or col == -1:
            return
        global_pos = self.table.mapToGlobal(pos)
        menu = QMenu(self)
        menu.addAction("Copy Selection", self.copy_selection_to_clipboard)
        menu.addAction("Mark Seen", lambda: self.update_status("Seen"))
        menu.addAction("Mark Applied", lambda: self.update_status("Applied"))
        menu.addAction("Reset Status", lambda: self.update_status(None))
        menu.addAction("Delete Job", self.delete_job)
        menu.popup(global_pos)

    def delete_job(self):
        """Delete selected jobs from DB and table with confirmation"""
        job_ids_to_delete = set()
        for item in self.table.selectedItems():
            row = item.row()
            job_id = int(self.table.item(row, 0).text())
            job_ids_to_delete.add(job_id)

        if not job_ids_to_delete:
            return

        if not self.never_show_delete_warning:
            warning = QMessageBox(self)
            checkbox = QCheckBox(warning)
            checkbox.setText("Never show this again")
            warning.setIcon(QMessageBox.Icon.Warning)
            warning.setWindowTitle("Confirm Deletion")
            warning.setText(f"This will delete {len(job_ids_to_delete)} job(s)!")
            warning.setStandardButtons(QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel)
            warning.setCheckBox(checkbox)
            ret = warning.exec()

            if ret != QMessageBox.StandardButton.Ok:
                logger.info("User cancelled delete operation")
                return

            if checkbox.isChecked():
                self.never_show_delete_warning = True
                self.settings.setValue("never_show_delete_warning", True)

        for job_id in job_ids_to_delete:
            try:
                self.db.delete_job(job_id)
                logger.info(f"Deleted job ID: {job_id}")
            except Exception as e:
                logger.error(f"Error deleting job {job_id}: {e}")

        self.load_jobs_with_filters()

    def save_excluded_words(self, titles, companies):
        """Save excluded titles and companies into the JSON file."""
        data = {
            "RAW_KEYWORDS_TO_EXCLUDE_TITLES": titles,
            "RAW_KEYWORDS_TO_EXCLUDE_COMPANIES": companies
        }
        with open(self.excluded_words_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load_excluded_words(self):
        """Load excluded titles and companies from the JSON file."""
        if not os.path.exists(self.excluded_words_file):
            logger.warning("Excluded words file not found, using defaults")
            return [], []

        with open(self.excluded_words_file, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
                titles = data.get("RAW_KEYWORDS_TO_EXCLUDE_TITLES", [])
                companies = data.get("RAW_KEYWORDS_TO_EXCLUDE_COMPANIES", [])
            except json.JSONDecodeError:
                logger.error("Error decoding excluded words file")
                return [], []

        return titles, companies

    def excluded_words(self):
        """Open dialog to manage excluded words"""
    
        dialog = QDialog(self)
        dialog.setWindowTitle("Manage Excluded Words")
        dialog.resize(500, 400) 
        dialog_layout = QVBoxLayout(dialog)
    
        title_label = QLabel("Excluded Titles (one per line):")
        title_text = QTextEdit()
        title_text.setPlainText("\n".join(self.exclude_titles)) 
        title_text.setMinimumHeight(150)  
        title_text.setPlaceholderText("Enter titles to exclude, one per line.")
        title_text.setStyleSheet("font-family: monospace;")
    
        company_label = QLabel("Excluded Companies (one per line):")
        company_text = QTextEdit()
        company_text.setPlainText("\n".join(self.exclude_companies))
        company_text.setMinimumHeight(150) 
        company_text.setPlaceholderText("Enter companies to exclude, one per line.")
        company_text.setStyleSheet("font-family: monospace;")
    
        dialog_layout.addWidget(title_label)
        dialog_layout.addWidget(title_text)
        dialog_layout.addWidget(company_label)
        dialog_layout.addWidget(company_text)
    
        button_layout = QHBoxLayout()
    
        def handle_save():
            try:
                new_titles = [t.strip() for t in title_text.toPlainText().splitlines() if t.strip()]
                new_companies = [c.strip() for c in company_text.toPlainText().splitlines() if c.strip()]

                self.save_excluded_words(new_titles, new_companies)
                self.exclude_titles = new_titles
                self.exclude_companies = new_companies

                dialog.accept()
                QMessageBox.information(self, "Success", "Excluded words saved successfully!")
                logger.info("Excluded words saved successfully")
            
            except Exception as e:
                logger.error(f"Failed to save excluded words: {e}")
                QMessageBox.warning(self, "Error", f"Failed to save excluded words: {e}")
    
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(handle_save)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dialog.reject)

        button_layout.addWidget(save_btn)
        button_layout.addWidget(cancel_btn)
        dialog_layout.addLayout(button_layout)

        dialog.exec()
            
    def ask_for_number(self, title="Select a number", label="Choose a value:", min_value=1, max_value=999):
        """Prompt user to select a number within a range"""

        dialog = QDialog(self)
        dialog.setWindowTitle(title)

        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel(label))

        combo = QComboBox(dialog)
        combo.addItems(map(str, range(min_value, max_value + 1)))
        layout.addWidget(combo)

        button_layout = QHBoxLayout()
        ok_btn = QPushButton("OK")
        ok_btn.clicked.connect(dialog.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dialog.reject)
        button_layout.addWidget(ok_btn)
        button_layout.addWidget(cancel_btn)
        layout.addLayout(button_layout)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            return int(combo.currentText())
        return None        
   
    def on_filter_change(self):
        """Handle changes in filter inputs"""
        hours_text = self.hours_input.text().strip()
        search_text = self.search_input.text().strip()
        hours_value = None
        if hours_text: 
            try:
                hours_value = int(hours_text)
            except ValueError:
                logger.warning(f"Invalid hours input: {hours_text}")

        self.filtering_functionality(hours_value, search_text)

    def filtering_functionality(self, hours, search_string):
        """Filter table rows based on hours and search string"""
        for row in range(self.table.rowCount()):
            title_item = self.table.item(row, 1)
            company_item = self.table.item(row, 2)
            location_item = self.table.item(row, 3)
            time_posted_item = self.table.item(row, 4)
            link_item = self.table.item(row, 5)
            type_item = self.table.item(row, 6)
        
            matches_time = True
            matches_search = True

            if time_posted_item and time_posted_item.text():
                try:
                    if hours is not None: 
                        posted_time = datetime.strptime(time_posted_item.text(), '%Y-%m-%d %H:%M:%S')
                        time_limit = datetime.now() - timedelta(hours=hours)
                        matches_time = posted_time >= time_limit
                    else:
                        matches_time = True 
                except Exception as e:
                    matches_time = True
                    logger.error(f"Error parsing time for filtering: {e}")

            if search_string.strip():
                try:  
                    search_lower = search_string.lower()
                    matches_search = any(
                        search_lower in (item.text().lower() if item else "")
                        for item in [title_item, company_item, location_item, link_item, type_item]
                    )
                except Exception as e:
                    matches_search = True
                    logger.error(f"Error during search filtering: {e}")
        
            should_show = matches_time and matches_search
            self.table.setRowHidden(row, not should_show)

    def hide_functionality(self, object, button):
        hide_rows = button.isChecked()

        for row in range(self.table.rowCount()):
            status_item = self.table.item(row, 8)

            if status_item and status_item.text() == object:
                if hide_rows:
                    button.setText(f"Show {object}")
                    self.table.hideRow(row)
                else:
                    button.setText(f"Hide {object}")
                    self.table.showRow(row)

    def show_full_description(self, row, column):
        if column == 7:
            text = self.table.item(row, column).text()
            QMessageBox.information(self, "Full Description", text)

    def load_jobs(self, limit=50):
        """Fetch jobs from DB and populate the table with proper formatting"""
        try:
            jobs = self.db.get_jobs(limit=limit)
            self.table.setRowCount(len(jobs))
            logger.info(f"Loading {len(jobs)} jobs into table")

            for row_idx, job in enumerate(jobs):

                self.table.setItem(row_idx, 0, QTableWidgetItem(str(job["id"])))

                title_item = QTableWidgetItem(job["title"] or "")
                title_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                self.table.setColumnWidth(1, 200)
                self.table.setItem(row_idx, 1, title_item)

                company_item = QTableWidgetItem(job["company_name"] or "")
                company_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                self.table.setColumnWidth(2, 150)
                self.table.setItem(row_idx, 2, company_item)

                location_item = QTableWidgetItem(job["company_location"] or "")
                location_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                self.table.setColumnWidth(3, 120)
                self.table.setItem(row_idx, 3, location_item)

                time_item = QTableWidgetItem(str(job["time_posted"]) if job["time_posted"] else "")
                time_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                self.table.setColumnWidth(4, 130)
                self.table.setItem(row_idx, 4, time_item)

                link_item = QTableWidgetItem(job["link"] or "")
                link_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                self.table.setColumnWidth(5, 100)
                self.table.setItem(row_idx, 5, link_item)

                type_item = QTableWidgetItem(job["type"] or "")
                type_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                self.table.setColumnWidth(6, 80)  
                self.table.setItem(row_idx, 6, type_item)

                description_TT = job["description"] or ""
                desc_item = QTableWidgetItem(job["description"] or "")
                desc_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
                desc_item.setToolTip(description_TT)
                self.table.setColumnWidth(7, 250)
                self.table.setItem(row_idx, 7, desc_item)

                status_item = QTableWidgetItem(job["status"] or "")
                status_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                self.table.setColumnWidth(8, 80)
                self.table.setItem(row_idx, 8, status_item)

                item = QTableWidgetItem("")
                item.setData(Qt.ItemDataRole.UserRole, job["is_new"])
                self.table.setItem(row_idx, 9, item)

                if job["is_new"]:
                    self.table.showRow(row_idx)

            self.table.setWordWrap(True)
            self.table.resizeColumnToContents(3)
            
        except Exception as e:
            logger.error(f"Error loading jobs: {e}")
            logger.debug(f"Job Data that failed: {job}")
            QMessageBox.warning(self, "Error", f"Failed to load jobs: {e}")

    def update_status(self, status):
        """Update the status of the selected job in DB and table"""
        selected_row = self.table.currentRow()
        if selected_row >= 0:
            try:
                job_id = int(self.table.item(selected_row, 0).text())
                self.db.update_job_status(job_id, status)
                self.db.mark_job_seen(job_id)
                self.table.setItem(selected_row, 8, QTableWidgetItem(status))  
                self.load_jobs_with_filters()
                logger.info(f"Job {job_id} marked as {status}")
            except Exception as e:
                logger.error(f"Error updating job status: {e}")
                QMessageBox.warning(self, "Error", f"Failed to update job status: {e}")

    def toggle_scraper(self):
        """Start or stop the scraper subprocess"""

        if self.scraper_process and self.scraper_process.poll() is None:
            QTimer.singleShot(3000, self.stop_scraper)
            self.scrape_button.setText("Stopping...")
            self.scrape_button.setEnabled(False)
        else:
            selected_hours = self.ask_for_number(
                title="Select Hours",
                label="How many hours back?",
                min_value=1,
                max_value=99
            )
            if selected_hours is not None:
                config = {"hours": selected_hours}
                logger.info(f"User selected scrape hours: {selected_hours}")
                try:
                    with open("scraper_config.json", 'w', encoding="utf-8") as f:
                        json.dump(config, f, ensure_ascii=False, indent=2)
                    self.start_scraper()
                    self.excluded_words_button.setEnabled(False)
                except Exception as e:
                    logger.error(f"Error writing config file: {e}")
                    QMessageBox.warning(self, "Error", "Could not save scraper configuration. Scraper will not start.")

    def start_scraper(self):
        """Start the standalone scraper subprocess"""
        try:
            for file_path in [self.status_file, self.jobs_file, self.stop_file]:
                if os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                    except:
                        pass
            
            self.processed_lines = 0
            
            # Get selected site from dropdown
            selected_site = self.site_dropdown.currentText()
            
            if getattr(sys, 'frozen', False):
                current_dir = os.path.dirname(sys.executable)
                scraper_executable = os.path.join(current_dir, "JobHunterScraper.exe")
            
                if not os.path.exists(scraper_executable):
                    logger.error(f"Scraper executable not found: {scraper_executable}")
                    QMessageBox.warning(self, "Error", f"Scraper executable not found: {scraper_executable}")
                    return
                
                cmd = [scraper_executable]
                work_dir = current_dir
            
            else:
                script_path = "standalone_scraper.py"
                if not os.path.exists(script_path):
                    logger.error(f"Scraper script not found: {script_path}")
                    QMessageBox.warning(self, "Error", f"Scraper script not found: {script_path}")
                    return
            
                cmd = [sys.executable, script_path]
                work_dir = os.getcwd()
        
            logger.info(f"Starting scraper with command: {cmd}")
            logger.info(f"Working directory: {work_dir}")
            logger.info(f"Selected site: {selected_site}")
            
            # Pass site via environment variable
            env = {**os.environ, "SCRAPER_SITE": selected_site}
        
            self.scraper_process = subprocess.Popen(
                cmd,
                cwd=work_dir,
                env=env,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0
            )
            
            self.scraper_timer.start(2000)
            self.scrape_button.setText("Stop Scraping")
            self.status_label.setText(f"Starting {selected_site} scraper...")
            
            logger.info(f"Started scraper subprocess with PID: {self.scraper_process.pid}")
            
        except Exception as e:
            logger.error(f"Error starting scraper: {e}")
            QMessageBox.critical(self, "Error", f"Failed to start scraper: {e}")

    def stop_scraper(self):
        """Stop the scraper subprocess gracefully"""
        try:
            with open(self.stop_file, 'w') as f:
                f.write("stop")
            
            self.status_label.setText("Stopping scraper...")
            logger.info("Stop flag created, waiting for scraper to stop...")
                
            if self.scraper_process:
                try:
                    self.scraper_process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    logger.warning("Scraper didn't stop gracefully, terminating...")
                    self.scraper_process.terminate()
                    try:
                        self.scraper_process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        logger.warning("Force killing scraper process...")
                        self.scraper_process.kill()
            
        except Exception as e:
            logger.error(f"Error stopping scraper: {e}")
        finally:
            self.scraper_cleanup()
            self.excluded_words_button.setEnabled(True)
            self.scrape_button.setEnabled(True)

    def scraper_cleanup(self):
        """Clean up after scraper stops"""
        self.scraper_timer.stop()
        self.scrape_button.setText("Scrape Now")
        self.status_label.setText("Ready")
        self.scraper_process = None
        self.excluded_words_button.setEnabled(True)
        
        for file_path in [self.stop_file]:
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except:
                    pass
        
        self.load_jobs_with_filters()
        QMessageBox.information(self, "Scraper", "Scraping Complete!")
        logger.info("Scraper cleanup complete")

    def check_scraper_status(self):
        """Check scraper status and process new job data"""
        if self.scraper_process and self.scraper_process.poll() is not None:
            logger.info("Scraper process has ended")
            self.scraper_cleanup()
            return
        
        try:
            if os.path.exists(self.status_file):
                with open(self.status_file, 'r', encoding='utf-8') as f:
                    status_data = json.load(f)
                
                status = status_data.get('status', 'unknown')
                message = status_data.get('message', '')
                jobs_scraped = status_data.get('jobs_scraped', 0)
                current_page = status_data.get('current_page', 1)
                
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
            logger.error(f"Error reading status file: {e}")
        
        self.process_new_jobs()

    def process_new_jobs(self):
        """Process new jobs from the JSONL file"""
        if not os.path.exists(self.jobs_file):
            return
        
        try:
            jobs_processed = 0
            with open(self.jobs_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            new_lines = lines[self.processed_lines:]
            
            for line in new_lines:
                line = line.strip()
                if not line:
                    continue
                
                try:
                    job_data = json.loads(line)

                    try:
                        self.db.insert_job_to_db(job_data)
                        jobs_processed += 1
                        logger.info(f"Successfully inserted: {job_data.get('Title', 'Unknown')}")
                    except Exception as e:
                        logger.error(f"Error inserting job to DB: {type(e).__name__}: {str(e)}")
                        logger.debug(f"Job data that failed: {job_data}")
                        
                except json.JSONDecodeError as e:
                    logger.error(f"Error parsing job data: {e}")
                    continue
            
            self.processed_lines = len(lines)
            
            if jobs_processed > 0:
                logger.info(f"Processed {jobs_processed} new jobs, refreshing table...")
                self.load_jobs_with_filters()
                
        except Exception as e:
            logger.error(f"Error processing job data: {e}")

    def closeEvent(self, event):
        """Handle application close - make sure to stop scraper process"""
        if self.scraper_process and self.scraper_process.poll() is None:
            logger.info("Application closing, stopping scraper...")
            self.stop_scraper()
            
            if self.scraper_process:
                try:
                    self.scraper_process.wait(timeout=6)
                except subprocess.TimeoutExpired:
                    logger.warning("Force killing scraper on app close...")
                    self.scraper_process.kill()
        
        if hasattr(self, 'db'):
            try:
                self.db.close()
                logger.info("Database connection closed")
            except Exception as e:
                logger.error(f"Error closing database: {e}")
        
        event.accept()

    def copy_selection_to_clipboard(self):
        """Copy selected table cells to clipboard in tab-separated format"""
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
        logger.info("Copied selection to clipboard")

        
# ---------------------------
# Main
# ---------------------------
if __name__ == "__main__":
    try:
        db = Database()
        app = QApplication(sys.argv)
        window = JobHelperApp(db)
        window.show()
        sys.exit(app.exec())
    except Exception as e:
        logging.critical(f"Failed to start application: {e}")
        sys.exit(1)