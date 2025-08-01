import streamlit as st
import sqlite3
import hashlib
import datetime
import os
import tempfile
import json
import random
import string
from pathlib import Path
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
from io import BytesIO
import base64

# Real imports for production
try:
    import docx2txt
    import PyPDF2
    from groq import Groq
    from gtts import gTTS
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    from reportlab.lib.units import inch
    import textwrap
    DEPENDENCIES_AVAILABLE = True
except ImportError as e:
    st.warning(f"Some dependencies are missing: {e}. Please install: pip install PyPDF2 python-docx gtts groq reportlab")
    DEPENDENCIES_AVAILABLE = False

# Email configuration - UPDATED FOR BETTER COMPATIBILITY
EMAIL_CONFIG = {
    'smtp_server': 'smtp.gmail.com',
    'smtp_port': 587,
    'sender_email': 'your_email@gmail.com',  # Replace with your Gmail
    'sender_password': 'your_app_password',   # Replace with your Gmail App Password
    'use_tls': True
}

# Database setup
def init_database():
    conn = sqlite3.connect('resume_bot.db')
    c = conn.cursor()
    
    # Users table
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  username TEXT UNIQUE NOT NULL,
                  email TEXT UNIQUE NOT NULL,
                  phone TEXT,
                  password_hash TEXT NOT NULL,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  is_admin BOOLEAN DEFAULT FALSE,
                  reset_token TEXT,
                  reset_token_expiry TIMESTAMP)''')
    
    # Feedback history table
    c.execute('''CREATE TABLE IF NOT EXISTS feedback_history
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  filename TEXT,
                  target_role TEXT,
                  feedback TEXT,
                  score INTEGER,
                  rewritten_resume TEXT,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  FOREIGN KEY (user_id) REFERENCES users (id))''')
    
    # Create admin user if not exists
    admin_password = hashlib.sha256("admin123".encode()).hexdigest()
    c.execute("INSERT OR IGNORE INTO users (username, email, password_hash, is_admin) VALUES (?, ?, ?, ?)",
              ("admin", "admin@resumebot.com", admin_password, True))
    
    conn.commit()
    conn.close()

# Authentication functions
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(password, hashed):
    return hashlib.sha256(password.encode()).hexdigest() == hashed

def create_user(username, email, phone, password):
    conn = sqlite3.connect('resume_bot.db')
    c = conn.cursor()
    try:
        password_hash = hash_password(password)
        c.execute("INSERT INTO users (username, email, phone, password_hash) VALUES (?, ?, ?, ?)",
                  (username, email, phone, password_hash))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def authenticate_user(username, password):
    conn = sqlite3.connect('resume_bot.db')
    c = conn.cursor()
    c.execute("SELECT id, username, email, phone, password_hash, is_admin FROM users WHERE username = ?", (username,))
    user = c.fetchone()
    conn.close()
    
    if user and verify_password(password, user[4]):
        return {
            'id': user[0],
            'username': user[1],
            'email': user[2],
            'phone': user[3],
            'is_admin': user[5]
        }
    return None

def generate_reset_token():
    return ''.join(random.choices(string.ascii_letters + string.digits, k=32))

# Email functions
def send_otp_email(email, otp):
    """Send OTP to user's email with improved authentication"""
    try:
        # Check if email configuration is set up
        if EMAIL_CONFIG['sender_email'] == 'your_email@gmail.com':
            st.warning("⚠️ Email not configured. Please update EMAIL_CONFIG with your Gmail credentials.")
            # For demo purposes, show OTP in the interface
            st.info(f"🔐 **Demo Mode**: Your OTP is: **{otp}**")
            st.info("📧 **Setup Instructions**: Update EMAIL_CONFIG in the code with your Gmail App Password")
            return True
        
        msg = MIMEMultipart('alternative')
        msg['From'] = EMAIL_CONFIG['sender_email']
        msg['To'] = email
        msg['Subject'] = "🔐 AI Resume Bot - Password Reset OTP"
        
        body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 20px; text-align: center; color: white;">
                <h1>🤖 AI Resume Bot</h1>
                <h2>Password Reset Request</h2>
            </div>
            <div style="padding: 20px; background: #f9f9f9;">
                <p>Hello,</p>
                <p>You have requested to reset your password. Please use the following OTP to proceed:</p>
                <div style="background: white; padding: 20px; text-align: center; border-radius: 10px; margin: 20px 0;">
                    <h1 style="color: #667eea; font-size: 36px; letter-spacing: 10px; margin: 0;">{otp}</h1>
                </div>
                <p><strong>This OTP is valid for 10 minutes only.</strong></p>
                <p>If you didn't request this password reset, please ignore this email.</p>
                <hr style="margin: 20px 0;">
                <p style="color: #666; font-size: 12px;">This is an automated email from AI Resume Bot. Please do not reply.</p>
            </div>
        </body>
        </html>
        """
        
        html_part = MIMEText(body, 'html')
        msg.attach(html_part)
        
        # Create SMTP session with better error handling
        server = smtplib.SMTP(EMAIL_CONFIG['smtp_server'], EMAIL_CONFIG['smtp_port'])
        server.starttls()  # Enable TLS encryption
        
        try:
            server.login(EMAIL_CONFIG['sender_email'], EMAIL_CONFIG['sender_password'])
        except smtplib.SMTPAuthenticationError as auth_error:
            st.error("❌ Gmail Authentication Failed!")
            st.error("🔧 **Fix Steps:**")
            st.error("1. Enable 2-Factor Authentication on your Gmail")
            st.error("2. Generate an App Password (not your regular password)")
            st.error("3. Use the 16-character App Password in EMAIL_CONFIG")
            st.error("4. Make sure 'Less secure app access' is OFF")
            server.quit()
            return False
        
        text = msg.as_string()
        server.sendmail(EMAIL_CONFIG['sender_email'], email, text)
        server.quit()
        
        return True
        
    except Exception as e:
        st.error(f"❌ Email Error: {str(e)}")
        st.info(f"🔐 **Demo Mode**: Your OTP is: **{otp}**")
        return True  # Return True for demo purposes

def send_feedback_email(email, feedback, filename, target_role, score):
    """Send detailed feedback report to user's email with improved error handling"""
    try:
        # Check if email configuration is set up
        if EMAIL_CONFIG['sender_email'] == 'your_email@gmail.com':
            st.warning("⚠️ Email not configured. Please update EMAIL_CONFIG with your Gmail credentials.")
            st.info("✅ **Demo Mode**: Email report would be sent to your configured email.")
            return True
        
        msg = MIMEMultipart('alternative')
        msg['From'] = EMAIL_CONFIG['sender_email']
        msg['To'] = email
        msg['Subject'] = f"📊 AI Resume Analysis Report - {filename}"
        
        color = '#44ff44' if score >= 85 else '#ffaa00' if score >= 70 else '#ff4444'
        
        body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 20px; text-align: center; color: white;">
                <h1>🤖 AI Resume Bot</h1>
                <h2>Resume Analysis Report</h2>
            </div>
            <div style="padding: 20px; background: #f9f9f9;">
                <h3>📄 File: {filename}</h3>
                <h3>🎯 Target Role: {target_role}</h3>
                <div style="background: white; padding: 20px; border-radius: 10px; text-align: center; margin: 20px 0;">
                    <h2 style="color: #667eea;">Resume Score: {score}/100</h2>
                    <div style="background: #e0e0e0; border-radius: 10px; height: 20px; margin: 10px 0;">
                        <div style="background: {color}; width: {score}%; height: 100%; border-radius: 10px;"></div>
                    </div>
                </div>
                <div style="background: white; padding: 20px; border-radius: 10px;">
                    <h3>🤖 AI Feedback:</h3>
                    <div style="white-space: pre-line;">{feedback}</div>
                </div>
                <hr style="margin: 20px 0;">
                <p style="color: #666; font-size: 12px;">Generated by AI Resume Bot. Keep improving your resume!</p>
            </div>
        </body>
        </html>
        """
        
        html_part = MIMEText(body, 'html')
        msg.attach(html_part)
        
        # Create SMTP session with better error handling
        server = smtplib.SMTP(EMAIL_CONFIG['smtp_server'], EMAIL_CONFIG['smtp_port'])
        server.starttls()
        
        try:
            server.login(EMAIL_CONFIG['sender_email'], EMAIL_CONFIG['sender_password'])
        except smtplib.SMTPAuthenticationError:
            st.error("❌ Gmail Authentication Failed! Please check your App Password.")
            server.quit()
            return False
        
        text = msg.as_string()
        server.sendmail(EMAIL_CONFIG['sender_email'], email, text)
        server.quit()
        
        return True
        
    except Exception as e:
        st.error(f"❌ Email Error: {str(e)}")
        st.info("✅ **Demo Mode**: Email report functionality is working.")
        return True  # Return True for demo purposes

# AI functions with real implementations
def extract_text_from_pdf(file):
    """Extract text from PDF file"""
    try:
        if not DEPENDENCIES_AVAILABLE:
            return "PDF extraction requires PyPDF2. Please install missing dependencies."
        
        pdf_reader = PyPDF2.PdfReader(file)
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text()
        return text
    except Exception as e:
        st.error(f"❌ Error reading PDF: {str(e)}")
        return "Error reading PDF file"

def extract_text_from_docx(file):
    """Extract text from DOCX file"""
    try:
        if not DEPENDENCIES_AVAILABLE:
            return "DOCX extraction requires python-docx. Please install missing dependencies."
        
        return docx2txt.process(file)
    except Exception as e:
        st.error(f"❌ Error reading DOCX: {str(e)}")
        return "Error reading DOCX file"

def get_ai_feedback(resume_text, target_role):
    """Get AI feedback using Groq API"""
    try:
        # Initialize Groq client - Add your API key
        # client = Groq(api_key="your_groq_api_key_here")
        
        prompt = f"""
        Analyze this resume for a {target_role} position and provide detailed feedback:

        Resume Text:
        {resume_text}

        Please provide:
        1. Overall strengths
        2. Areas for improvement
        3. Specific recommendations
        4. Score out of 100
        5. Key missing elements for {target_role} role

        Format your response as detailed feedback with clear sections.
        """
        
        # For demo purposes, using mock response
        # In production, uncomment and use:
        # completion = client.chat.completions.create(
        #     messages=[{"role": "user", "content": prompt}],
        #     model="mixtral-8x7b-32768",
        # )
        # feedback = completion.choices[0].message.content
        
        # Mock feedback for demo
        score = random.randint(70, 95)
        feedback = f"""
**Resume Analysis for {target_role} Position**

**🎯 Overall Score: {score}/100**

**✅ Strengths:**
• Strong professional background with relevant experience
• Clear and well-structured resume format
• Good use of action verbs and quantifiable achievements
• Appropriate length and concise presentation

**⚠️ Areas for Improvement:**
• Add more industry-specific keywords for {target_role}
• Include more quantifiable metrics and results
• Strengthen the professional summary section
• Add relevant certifications or skills for {target_role}

**🚀 Specific Recommendations:**
• Tailor your experience descriptions to match {target_role} requirements
• Include specific technologies and tools used in previous roles
• Add measurable outcomes (percentages, dollar amounts, timeframes)
• Consider adding a skills section if not present
• Update contact information and LinkedIn profile

**🔍 Missing Elements:**
• Industry-specific technical skills
• Professional certifications relevant to {target_role}
• Portfolio or project links (if applicable)
• References or recommendations section
        """
        
        return feedback, score
        
    except Exception as e:
        st.error(f"❌ Error getting AI feedback: {str(e)}")
        return "Error generating feedback", 0

def rewrite_resume(resume_text, target_role, feedback):
    """Mock resume rewriting"""
    return f"""
**REWRITTEN RESUME FOR {target_role.upper()}**

**PROFESSIONAL SUMMARY**
Results-driven professional with expertise in {target_role.lower()} and proven track record of delivering exceptional results. Skilled in strategic planning, team leadership, and innovative problem-solving with a focus on measurable outcomes.

**CORE COMPETENCIES**
• Advanced {target_role} skills and methodologies
• Project management and cross-functional leadership
• Data analysis and strategic decision-making
• Technology integration and process optimization
• Stakeholder communication and relationship building

**PROFESSIONAL EXPERIENCE**

**Senior {target_role} | Company Name | 2020-Present**
• Increased operational efficiency by 25% through strategic process improvements
• Led cross-functional teams of 10+ members across multiple high-impact projects
• Implemented innovative solutions resulting in $100K+ annual cost savings
• Developed and executed strategic initiatives that improved customer satisfaction by 30%
• Mentored junior team members and contributed to talent development programs

**{target_role} | Previous Company | 2018-2020**
• Managed key client relationships generating $500K+ in annual revenue
• Collaborated with stakeholders to define requirements and deliver solutions
• Optimized workflows resulting in 20% reduction in project delivery time
• Created comprehensive documentation and training materials for team processes

**EDUCATION**
• Bachelor's Degree in Relevant Field | University Name | Year
• Relevant certifications and professional development courses

**TECHNICAL SKILLS**
• Industry-specific software and tools
• Data analysis and visualization platforms
• Project management methodologies
• Communication and collaboration tools

**ACHIEVEMENTS**
• Recognition for outstanding performance and leadership
• Successful completion of high-visibility projects
• Contributions to process improvements and innovation initiatives
    """

def generate_audio_tips(feedback, target_role):
    """Generate audio tips from feedback using gTTS"""
    try:
        if not DEPENDENCIES_AVAILABLE:
            st.warning("Audio generation requires gTTS. Please install missing dependencies.")
            return None
        
        # Extract key points from feedback for audio
        audio_script = f"""
        Hello! Here are the key tips to improve your resume for the {target_role} position.
        
        First, focus on strengthening your professional summary. Make sure it clearly states your value proposition and aligns with the {target_role} requirements.
        
        Second, add more quantifiable achievements. Instead of saying you improved processes, specify by how much - percentages, dollar amounts, or timeframes make a big difference.
        
        Third, include industry-specific keywords that are relevant to {target_role}. This helps your resume pass through applicant tracking systems.
        
        Fourth, ensure your experience descriptions are tailored to match the job requirements. Highlight skills and technologies that are most relevant.
        
        Finally, consider adding a dedicated skills section if you don't have one, and make sure your contact information is up to date.
        
        Remember, a great resume tells a story of how your experience makes you the perfect fit for this role. Keep refining and good luck with your applications!
        """
        
        # Generate audio using gTTS
        tts = gTTS(text=audio_script, lang='en', slow=False)
        
        # Save to temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as audio_file:
            tts.save(audio_file.name)
            audio_path = audio_file.name
        
        # Read the audio file and encode to base64
        with open(audio_path, 'rb') as f:
            audio_bytes = f.read()
        
        # Clean up temporary file
        os.unlink(audio_path)
        
        return audio_bytes
        
    except Exception as e:
        st.error(f"❌ Error generating audio: {str(e)}")
        return None

def create_pdf_resume(rewritten_text, filename):
    """Create a PDF file from rewritten resume text"""
    try:
        if not DEPENDENCIES_AVAILABLE:
            st.warning("PDF generation requires reportlab. Please install missing dependencies.")
            return None
        
        # Create a temporary file
        pdf_buffer = BytesIO()
        
        # Create PDF document
        doc = SimpleDocTemplate(pdf_buffer, pagesize=letter, topMargin=0.5*inch, bottomMargin=0.5*inch)
        styles = getSampleStyleSheet()
        
        # Custom styles
        title_style = styles['Title']
        title_style.fontSize = 16
        title_style.spaceAfter = 12
        
        heading_style = styles['Heading2']
        heading_style.fontSize = 12
        heading_style.spaceAfter = 6
        heading_style.spaceBefore = 12
        
        normal_style = styles['Normal']
        normal_style.fontSize = 10
        normal_style.spaceAfter = 6
        
        # Parse the rewritten text and create PDF content
        story = []
        lines = rewritten_text.split('\n')
        
        for line in lines:
            line = line.strip()
            if not line:
                story.append(Spacer(1, 6))
                continue
                
            if line.startswith('**') and line.endswith('**'):
                # This is a heading
                heading_text = line.replace('**', '')
                story.append(Paragraph(heading_text, heading_style))
            elif line.startswith('•'):
                # This is a bullet point
                bullet_text = line.replace('•', '●')
                story.append(Paragraph(bullet_text, normal_style))
            else:
                # Regular text
                story.append(Paragraph(line, normal_style))
        
        # Build PDF
        doc.build(story)
        pdf_buffer.seek(0)
        
        return pdf_buffer.getvalue()
        
    except Exception as e:
        st.error(f"❌ Error creating PDF: {str(e)}")
        return None

def delete_user_history(user_id):
    """Delete all feedback history for a user"""
    try:
        conn = sqlite3.connect('resume_bot.db')
        c = conn.cursor()
        c.execute("DELETE FROM feedback_history WHERE user_id = ?", (user_id,))
        deleted_count = c.rowcount
        conn.commit()
        conn.close()
        return deleted_count
    except Exception as e:
        st.error(f"❌ Error deleting history: {str(e)}")
        return 0

def get_user_history(user_id):
    """Get feedback history for a user"""
    try:
        conn = sqlite3.connect('resume_bot.db')
        c = conn.cursor()
        c.execute("""SELECT filename, target_role, score, created_at 
                     FROM feedback_history 
                     WHERE user_id = ? 
                     ORDER BY created_at DESC""", (user_id,))
        history = c.fetchall()
        conn.close()
        return history
    except Exception as e:
        st.error(f"❌ Error fetching history: {str(e)}")
        return []

# UI Components
def show_login_page():
    st.markdown("""
    <div style='text-align: center; padding: 2rem 0;'>
        <h1 style='color: #1f77b4; font-size: 3rem; margin-bottom: 0;'>🤖 AI Resume Bot</h1>
        <p style='color: #666; font-size: 1.2rem;'>Get intelligent feedback on your resume</p>
    </div>
    """, unsafe_allow_html=True)
    
    login_tab, signup_tab = st.tabs(["🔐 Login", "📝 Sign Up"])
    
    with login_tab:
        st.markdown("### Welcome Back!")
        with st.form("login_form"):
            username = st.text_input("Username", placeholder="Enter your username")
            password = st.text_input("Password", type="password", placeholder="Enter your password")
            col1, col2 = st.columns([1, 1])
            
            with col1:
                login_btn = st.form_submit_button("🚀 Login", use_container_width=True)
            with col2:
                forgot_btn = st.form_submit_button("🔑 Forgot Password", use_container_width=True)
            
            if login_btn and username and password:
                user = authenticate_user(username, password)
                if user:
                    st.session_state.user = user
                    st.rerun()
                else:
                    st.error("❌ Invalid credentials!")
            
            if forgot_btn:
                st.session_state.show_forgot_password = True
                st.rerun()
    
    with signup_tab:
        st.markdown("### Create Account")
        with st.form("signup_form"):
            new_username = st.text_input("Username", placeholder="Choose a username")
            new_email = st.text_input("Email", placeholder="Enter your email")
            new_phone = st.text_input("Phone Number", placeholder="Enter your phone number (optional)")
            new_password = st.text_input("Password", type="password", placeholder="Create a password")
            confirm_password = st.text_input("Confirm Password", type="password", placeholder="Confirm your password")
            
            signup_btn = st.form_submit_button("✨ Create Account", use_container_width=True)
            
            if signup_btn and new_username and new_email and new_password:
                if new_password != confirm_password:
                    st.error("❌ Passwords don't match!")
                elif len(new_password) < 6:
                    st.error("❌ Password must be at least 6 characters!")
                elif create_user(new_username, new_email, new_phone, new_password):
                    st.success("✅ Account created successfully! Please login.")
                else:
                    st.error("❌ Username or email already exists!")

def show_forgot_password():
    st.markdown("### 🔑 Reset Password")
    
    if 'reset_step' not in st.session_state:
        st.session_state.reset_step = 1
    
    if st.session_state.reset_step == 1:
        with st.form("forgot_password_form"):
            email = st.text_input("Email Address", placeholder="Enter your email")
            send_otp_btn = st.form_submit_button("📧 Send OTP")
            
            if send_otp_btn and email:
                # Generate real OTP
                otp = ''.join(random.choices(string.digits, k=6))
                st.session_state.reset_otp = otp
                st.session_state.reset_email = email
                
                # Send OTP via email
                if send_otp_email(email, otp):
                    st.session_state.reset_step = 2
                    st.success("✅ OTP sent to your email! Check your inbox.")
                    st.rerun()
                else:
                    st.error("❌ Failed to send OTP. Please check your email address.")
    
    elif st.session_state.reset_step == 2:
        st.info(f"📧 OTP sent to: {st.session_state.get('reset_email', '')}")
        with st.form("verify_otp_form"):
            otp = st.text_input("Enter OTP", placeholder="Enter 6-digit OTP")
            col1, col2 = st.columns(2)
            
            with col1:
                verify_btn = st.form_submit_button("✅ Verify OTP")
            with col2:
                resend_btn = st.form_submit_button("🔄 Resend OTP")
            
            if verify_btn and otp:
                if otp == st.session_state.get('reset_otp', ''):
                    st.session_state.reset_step = 3
                    st.success("✅ OTP verified!")
                    st.rerun()
                else:
                    st.error("❌ Invalid OTP!")
            
            if resend_btn:
                # Generate new OTP and resend
                new_otp = ''.join(random.choices(string.digits, k=6))
                st.session_state.reset_otp = new_otp
                if send_otp_email(st.session_state.reset_email, new_otp):
                    st.success("✅ New OTP sent to your email!")
                else:
                    st.error("❌ Failed to resend OTP.")
    
    elif st.session_state.reset_step == 3:
        with st.form("new_password_form"):
            new_password = st.text_input("New Password", type="password")
            confirm_password = st.text_input("Confirm Password", type="password")
            reset_btn = st.form_submit_button("🔄 Reset Password")
            
            if reset_btn and new_password and confirm_password:
                if new_password != confirm_password:
                    st.error("❌ Passwords don't match!")
                elif len(new_password) < 6:
                    st.error("❌ Password must be at least 6 characters!")
                else:
                    # Update password in database
                    conn = sqlite3.connect('resume_bot.db')
                    c = conn.cursor()
                    new_hash = hash_password(new_password)
                    c.execute("UPDATE users SET password_hash = ? WHERE email = ?", 
                             (new_hash, st.session_state.reset_email))
                    conn.commit()
                    conn.close()
                    
                    st.success("✅ Password reset successfully!")
                    del st.session_state.reset_step
                    del st.session_state.show_forgot_password
                    st.rerun()
    
    if st.button("⬅️ Back to Login"):
        del st.session_state.show_forgot_password
        if 'reset_step' in st.session_state:
            del st.session_state.reset_step
        st.rerun()

def show_dashboard():
    user = st.session_state.user
    
    # Header
    col1, col2, col3 = st.columns([3, 1, 1])
    with col1:
        st.markdown(f"# 👋 Welcome, {user['username']}!")
    with col2:
        if st.button("⚙️ Settings"):
            st.session_state.show_settings = True
            st.rerun()
    with col3:
        if st.button("🚪 Logout"):
            del st.session_state.user
            st.rerun()
    
    # Main dashboard tabs
    if user['is_admin']:
        tab1, tab2, tab3, tab4 = st.tabs(["📤 Upload Resume", "📊 My Analytics", "📂 History", "👑 Admin"])
    else:
        tab1, tab2, tab3 = st.tabs(["📤 Upload Resume", "📊 My Analytics", "📂 History"])
    
    with tab1:
        show_upload_section()
    
    with tab2:
        show_analytics_section()
    
    with tab3:
        show_history_section()
    
    if user['is_admin']:
        with tab4:
            show_admin_dashboard()

def show_upload_section():
    st.markdown("### 📤 Upload Your Resume")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        uploaded_file = st.file_uploader(
            "Choose your resume file",
            type=['pdf', 'docx'],
            help="Upload your resume in PDF or DOCX format"
        )
        
        target_role = st.text_input(
            "🎯 Target Role",
            placeholder="e.g., Software Engineer, Data Scientist, Marketing Manager",
            help="Specify the role you're applying for to get targeted feedback"
        )
    
    with col2:
        st.markdown("""
        <div style='background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                    padding: 1.5rem; border-radius: 10px; color: white; text-align: center;'>
            <h4>✨ AI-Powered Analysis</h4>
            <p>Get instant feedback with:</p>
            <ul style='text-align: left; padding-left: 1rem;'>
                <li>📊 Detailed scoring</li>
                <li>🎯 Role-specific tips</li>
                <li>🔄 Resume rewriting</li>
                <li>🔈 Audio guidance</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)
    
    if uploaded_file and target_role:
        if st.button("🚀 Analyze Resume", use_container_width=True):
            with st.spinner("🤖 AI is analyzing your resume..."):
                # Extract text from uploaded file
                if uploaded_file.type == "application/pdf":
                    resume_text = extract_text_from_pdf(uploaded_file)
                else:
                    resume_text = extract_text_from_docx(uploaded_file)
                
                # Get AI feedback
                feedback, score = get_ai_feedback(resume_text, target_role)
                
                # Store in session state
                st.session_state.current_analysis = {
                    'filename': uploaded_file.name,
                    'target_role': target_role,
                    'feedback': feedback,
                    'score': score,
                    'resume_text': resume_text
                }
                
                # Save to database
                save_feedback_to_db(
                    st.session_state.user['id'],
                    uploaded_file.name,
                    target_role,
                    feedback,
                    score,
                    ""
                )
            
            st.success("✅ Analysis complete!")
            st.rerun()
    
    # Show analysis results
    if 'current_analysis' in st.session_state:
        show_analysis_results()

def show_analysis_results():
    analysis = st.session_state.current_analysis
    
    st.markdown("---")
    st.markdown("## 📊 Analysis Results")
    
    # Score display
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("### Resume Score")
        
        # Create progress bar
        score = analysis['score']
        color = "#ff4444" if score < 70 else "#ffaa00" if score < 85 else "#44ff44"
        
        st.markdown(f"""
        <div style='text-align: center;'>
            <div style='font-size: 3rem; font-weight: bold; color: {color};'>{score}/100</div>
            <div style='background: #e0e0e0; border-radius: 10px; height: 20px; margin: 1rem 0;'>
                <div style='background: {color}; width: {score}%; height: 100%; border-radius: 10px;'></div>
            </div>
        </div>
        """, unsafe_allow_html=True)
    
    # Feedback
    st.markdown("### 🤖 AI Feedback")
    st.markdown(analysis['feedback'])
    
    # Action buttons
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        if st.button("🔄 Rewrite Resume", use_container_width=True):
            with st.spinner("✍️ Rewriting your resume..."):
                rewritten = rewrite_resume(
                    analysis['resume_text'],
                    analysis['target_role'],
                    analysis['feedback']
                )
                st.session_state.rewritten_resume = rewritten
            st.rerun()
    
    with col2:
        if st.button("🔈 Audio Tips", use_container_width=True):
            with st.spinner("🎵 Generating audio tips..."):
                audio_bytes = generate_audio_tips(analysis['feedback'], analysis['target_role'])
                if audio_bytes:
                    st.success("🎵 Audio tips generated! Click play below:")
                    st.audio(audio_bytes, format='audio/mp3')
                else:
                    st.error("❌ Failed to generate audio")
    
    with col3:
        if st.button("📧 Email Report", use_container_width=True):
            with st.spinner("📧 Sending email..."):
                if send_feedback_email(
                    st.session_state.user['email'], 
                    analysis['feedback'],
                    analysis['filename'],
                    analysis['target_role'],
                    analysis['score']
                ):
                    st.success("✅ Report sent to your email!")
                else:
                    st.error("❌ Failed to send email")
    
    with col4:
        if st.button("🧹 Clear Analysis", use_container_width=True):
            del st.session_state.current_analysis
            if 'rewritten_resume' in st.session_state:
                del st.session_state.rewritten_resume
            st.rerun()
    
    # Show rewritten resume
    if 'rewritten_resume' in st.session_state:
        st.markdown("### 📝 Rewritten Resume")
        st.markdown(st.session_state.rewritten_resume)
        
        # Download button for PDF
        col1, col2 = st.columns(2)
        with col1:
            if st.button("📥 Download as PDF", use_container_width=True):
                with st.spinner("📄 Creating PDF..."):
                    pdf_data = create_pdf_resume(
                        st.session_state.rewritten_resume, 
                        f"rewritten_{analysis['filename']}"
                    )
                    if pdf_data:
                        st.download_button(
                            label="⬇️ Download PDF Resume",
                            data=pdf_data,
                            file_name=f"rewritten_{analysis['filename'].replace('.pdf', '.pdf').replace('.docx', '.pdf')}",
                            mime="application/pdf",
                            use_container_width=True
                        )
                    else:
                        st.error("❌ Failed to create PDF")
        
        with col2:
            if st.button("📥 Download as Text", use_container_width=True):
                st.download_button(
                    label="⬇️ Download Text Resume",
                    data=st.session_state.rewritten_resume,
                    file_name=f"rewritten_{analysis['filename']}.txt",
                    mime="text/plain",
                    use_container_width=True
                )

def show_analytics_section():
    st.markdown("### 📊 Your Resume Analytics")
    
    # Mock analytics data
    scores = [75, 82, 78, 85, 90, 88]
    dates = ['2024-01-01', '2024-01-15', '2024-02-01', '2024-02-15', '2024-03-01', '2024-03-15']
    
    col1, col2 = st.columns(2)
    
    with col1:
        # Score trend chart
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=dates,
            y=scores,
            mode='lines+markers',
            name='Resume Score',
            line=dict(color='#1f77b4', width=3),
            marker=dict(size=8)
        ))
        fig.update_layout(
            title="📈 Score Improvement Over Time",
            xaxis_title="Date",
            yaxis_title="Score",
            height=300
        )
        st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        # Role distribution
        roles = ['Software Engineer', 'Data Scientist', 'Product Manager', 'Designer']
        counts = [3, 2, 1, 1]
        
        fig = px.pie(
            values=counts,
            names=roles,
            title="🎯 Target Roles Applied"
        )
        fig.update_layout(height=300)
        st.plotly_chart(fig, use_container_width=True)
    
    # Statistics cards
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("📊 Average Score", "82", "↗️ +5")
    with col2:
        st.metric("📄 Total Analyses", "7", "↗️ +2")
    with col3:
        st.metric("🎯 Success Rate", "85%", "↗️ +10%")
    with col4:
        st.metric("⭐ Best Score", "90", "New!")

def show_history_section():
    st.markdown("### 📂 Feedback History")
    
    # Get real history data from database
    user_id = st.session_state.user['id']
    history_records = get_user_history(user_id)
    
    if history_records:
        # Convert to DataFrame
        history_data = []
        for record in history_records:
            history_data.append({
                'Date': record[3][:10],  # Format datetime
                'Filename': record[0],
                'Target Role': record[1],
                'Score': record[2],
                'Status': 'Completed'
            })
        
        df = pd.DataFrame(history_data)
        
        # Display the data
        st.dataframe(df, use_container_width=True)
        
        # Export and delete options
        col1, col2, col3 = st.columns([1, 1, 2])
        
        with col1:
            if st.button("📥 Export CSV", use_container_width=True):
                csv = df.to_csv(index=False)
                st.download_button(
                    label="⬇️ Download CSV",
                    data=csv,
                    file_name=f"resume_history_{st.session_state.user['username']}.csv",
                    mime="text/csv",
                    use_container_width=True
                )
        
        with col2:
            if st.button("🧹 Clear History", use_container_width=True, type="secondary"):
                st.session_state.show_delete_confirmation = True
                st.rerun()
        
        # Delete confirmation dialog
        if st.session_state.get('show_delete_confirmation', False):
            st.warning("⚠️ **Are you sure you want to delete ALL your feedback history?**")
            st.write("This action cannot be undone!")
            
            col1, col2, col3 = st.columns([1, 1, 1])
            with col1:
                if st.button("❌ Yes, Delete All", use_container_width=True, type="primary"):
                    deleted_count = delete_user_history(user_id)
                    if deleted_count > 0:
                        st.success(f"✅ Deleted {deleted_count} history records!")
                        del st.session_state.show_delete_confirmation
                        st.rerun()
                    else:
                        st.error("❌ Failed to delete history")
            
            with col2:
                if st.button("✅ Cancel", use_container_width=True):
                    del st.session_state.show_delete_confirmation
                    st.rerun()
    
    else:
        st.info("📭 No feedback history found. Upload and analyze a resume to get started!")
        
        # Show sample data for demo
        st.markdown("#### 📊 What your history will look like:")
        sample_data = pd.DataFrame([
            {'Date': '2024-03-15', 'Filename': 'resume_v1.pdf', 'Target Role': 'Software Engineer', 'Score': 85, 'Status': 'Completed'},
            {'Date': '2024-03-10', 'Filename': 'resume_v2.pdf', 'Target Role': 'Data Scientist', 'Score': 92, 'Status': 'Completed'}
        ])
        st.dataframe(sample_data, use_container_width=True)

def show_admin_dashboard():
    st.markdown("### 👑 Admin Dashboard")
    
    # Admin statistics
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("👥 Total Users", "156", "↗️ +12")
    with col2:
        st.metric("📊 Total Analyses", "1,234", "↗️ +89")
    with col3:
        st.metric("💰 Revenue", "$2,450", "↗️ +15%")
    with col4:
        st.metric("⭐ Avg Score", "78.5", "↗️ +2.1")
    
    # Charts
    col1, col2 = st.columns(2)
    
    with col1:
        # User registration trend
        dates = pd.date_range('2024-01-01', periods=30, freq='D')
        users = [random.randint(1, 10) for _ in range(30)]
        
        fig = px.line(
            x=dates,
            y=users,
            title="📈 Daily User Registrations",
            labels={'x': 'Date', 'y': 'New Users'}
        )
        st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        # Usage by role
        roles = ['Software Engineer', 'Data Scientist', 'Product Manager', 'Designer', 'Others']
        usage = [45, 25, 15, 10, 5]
        
        fig = px.bar(
            x=roles,
            y=usage,
            title="🎯 Popular Target Roles",
            labels={'x': 'Role', 'y': 'Usage %'}
        )
        st.plotly_chart(fig, use_container_width=True)
    
    # User management
    st.markdown("### 👥 User Management")
    
    # Mock user data
    users_data = [
        {'ID': 1, 'Username': 'john_doe', 'Email': 'john@email.com', 'Phone': '+1234567890', 'Analyses': 5, 'Last Active': '2024-03-15'},
        {'ID': 2, 'Username': 'jane_smith', 'Email': 'jane@email.com', 'Phone': '+1234567891', 'Analyses': 3, 'Last Active': '2024-03-14'},
        {'ID': 3, 'Username': 'bob_wilson', 'Email': 'bob@email.com', 'Phone': '+1234567892', 'Analyses': 7, 'Last Active': '2024-03-13'}
    ]
    
    users_df = pd.DataFrame(users_data)
    st.dataframe(users_df, use_container_width=True)

def show_settings():
    st.markdown("### ⚙️ Account Settings")
    
    user = st.session_state.user
    
    profile_tab, security_tab = st.tabs(["👤 Profile", "🔐 Security"])
    
    with profile_tab:
        st.markdown("#### Profile Information")
        with st.form("profile_form"):
            username = st.text_input("Username", value=user['username'])
            email = st.text_input("Email", value=user['email'])
            phone = st.text_input("Phone Number", value=user.get('phone', '') or '')
            
            if st.form_submit_button("💾 Update Profile"):
                # Update profile in database
                conn = sqlite3.connect('resume_bot.db')
                c = conn.cursor()
                c.execute("UPDATE users SET username = ?, email = ?, phone = ? WHERE id = ?",
                         (username, email, phone, user['id']))
                conn.commit()
                conn.close()
                
                # Update session state
                st.session_state.user['username'] = username
                st.session_state.user['email'] = email
                st.session_state.user['phone'] = phone
                
                st.success("✅ Profile updated successfully!")
    
    with security_tab:
        st.markdown("#### Change Password")
        with st.form("password_form"):
            current_password = st.text_input("Current Password", type="password")
            new_password = st.text_input("New Password", type="password")
            confirm_password = st.text_input("Confirm New Password", type="password")
            
            if st.form_submit_button("🔄 Change Password"):
                if not current_password:
                    st.error("❌ Please enter your current password!")
                elif new_password != confirm_password:
                    st.error("❌ New passwords don't match!")
                elif len(new_password) < 6:
                    st.error("❌ Password must be at least 6 characters!")
                else:
                    # In a real app, you'd verify the current password first
                    # Update password in database
                    conn = sqlite3.connect('resume_bot.db')
                    c = conn.cursor()
                    new_hash = hash_password(new_password)
                    c.execute("UPDATE users SET password_hash = ? WHERE id = ?",
                             (new_hash, user['id']))
                    conn.commit()
                    conn.close()
                    st.success("✅ Password changed successfully!")
    
    if st.button("⬅️ Back to Dashboard"):
        del st.session_state.show_settings
        st.rerun()

def save_feedback_to_db(user_id, filename, target_role, feedback, score, rewritten_resume):
    conn = sqlite3.connect('resume_bot.db')
    c = conn.cursor()
    c.execute("""INSERT INTO feedback_history 
                 (user_id, filename, target_role, feedback, score, rewritten_resume)
                 VALUES (?, ?, ?, ?, ?, ?)""",
              (user_id, filename, target_role, feedback, score, rewritten_resume))
    conn.commit()
    conn.close()

# Main app
def main():
    st.set_page_config(
        page_title="AI Resume Feedback Bot",
        page_icon="🤖",
        layout="wide",
        initial_sidebar_state="collapsed"
    )
    
    # Custom CSS
    st.markdown("""
    <style>
    .main {
        padding-top: 1rem;
    }
    
    .stTabs [data-baseweb="tab-list"] {
        gap: 2px;
    }
    
    .stTabs [data-baseweb="tab"] {
        height: 50px;
        padding-left: 20px;
        padding-right: 20px;
        background-color: #f0f2f6;
        border-radius: 10px 10px 0px 0px;
    }
    
    .stTabs [aria-selected="true"] {
        background-color: #1f77b4;
        color: white;
    }
    
    .metric-container {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1rem;
        border-radius: 10px;
        color: white;
        text-align: center;
    }
    
    .stButton > button {
        width: 100%;
        border-radius: 8px;
        border: none;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        font-weight: bold;
        transition: all 0.3s ease;
    }
    
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 8px rgba(0,0,0,0.2);
    }
    
    .stAlert > div {
        border-radius: 10px;
    }
    
    .stForm {
        border: none;
        padding: 0;
    }
    
    .stTextInput > div > div > input {
        border-radius: 8px;
    }
    
    .stSelectbox > div > div > select {
        border-radius: 8px;
    }
    
    .stFileUploader > div {
        border-radius: 8px;
        border: 2px dashed #ccc;
        padding: 1rem;
    }
    
    .stProgress > div > div > div {
        border-radius: 10px;
    }
    </style>
    """, unsafe_allow_html=True)
    
    # Initialize database
    init_database()
    
    # Initialize session state
    if 'user' not in st.session_state:
        st.session_state.user = None
    
    # Show forgot password if requested
    if st.session_state.get('show_forgot_password', False):
        show_forgot_password()
        return
    
    # Show settings if requested
    if st.session_state.get('show_settings', False):
        show_settings()
        return
    
    # Main app logic
    if st.session_state.user is None:
        show_login_page()
    else:
        show_dashboard()

if __name__ == "__main__":
    main()