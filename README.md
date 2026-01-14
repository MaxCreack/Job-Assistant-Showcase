# Job Hunt Assistant  

**A desktop application that helps job seekers streamline their search with automated scraping, database tracking, and an intuitive GUI.**  

This project combines **Python, Selenium, PostgreSQL+SQLite, and PyQt6** to create a complete workflow: jobs are scraped automatically from job boards, stored in a structured database, and presented in a user-friendly interface where applicants can track their progress. 

ANY "SENSITIVE" INFORMATION HAS BEEN COVERED (Company Names, Links etc)

## Features  

• **Intelligent Web Scraping System:** Developed an automated job search tool using Selenium and Chrome automation that intelligently collects job listings from multiple websites while evading bot detection

• **Clean, Intuitive Desktop Interface:** Built a PyQt5 application with a searchable job listing table where users can view, filter, and manage opportunities all in one place

• **Local Database Storage:** Implemented a SQLite database with proper data relationships and constraints, storing job information securely on the user's computer for reliable access and historical searches

• **Anti-Detection Technology:** Engineered stealth browser techniques including JavaScript injection, randomized scrolling patterns, and user-agent spoofing to maintain reliable scraping without blocking

• **Advanced Search & Filtering:** Created intelligent filtering that lets users search by keywords, job posting date, company, and job type—with one-click hide/show toggles for unwanted listings

• **Smart Resource Management:** Designed automatic cleanup processes that terminate Chrome processes, clear temporary files, and manage memory efficiently to prevent system slowdown

• **Production-Ready Executable:** Packaged the entire application as standalone executables using PyInstaller, allowing non-technical users to run the tool without Python knowledge

• **Robust Error Handling & Logging:** Implemented comprehensive logging across all modules with graceful failure handling, signal interception (SIGTERM/SIGINT), and detailed status reporting for troubleshooting

## Tech Stack  

• **Language:** Python 3  
• **Frontend:** PyQt6 (desktop GUI)  
• **Database:** PostgreSQL + SQLite (For production distrubtion)
• **Scraping:** Selenium + undetected-chromedriver  
• **Other Tools:** dotenv, psutil  

<img width="3839" height="2062" alt="Screenshot 2025-09-09 124253" src="https://github.com/user-attachments/assets/bd016530-6e94-4188-85e4-f0530b696744" />
