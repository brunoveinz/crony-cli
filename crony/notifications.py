import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
import logging
from typing import Dict, List, Optional
from pathlib import Path

from crony.i18n import get_translator

LOG = logging.getLogger("crony.notifications")

class EmailNotifier:
    def __init__(self, config: Dict):
        self.config = config
        self.enabled = config.get('enabled', False)
        if not self.enabled:
            return
            
        smtp_config = config.get('smtp', {})
        self.server = smtp_config.get('server')
        self.port = smtp_config.get('port', 587)
        self.username = smtp_config.get('username')
        self.password = smtp_config.get('password')
        self.use_tls = smtp_config.get('use_tls', True)
        self.recipients = config.get('recipients', [])
        
        if not all([self.server, self.port, self.username, self.password, self.recipients]):
            LOG.warning("Email notifications enabled but configuration incomplete")
            self.enabled = False

    def send_notification(self, subject: str, body: str, job_name: str = "",
                         include_logs: bool = False, log_content: str = "",
                         is_success: bool = True):
        if not self.enabled:
            return

        try:
            msg = MIMEMultipart('alternative')
            msg['From'] = self.username
            msg['To'] = ', '.join(self.recipients)
            msg['Subject'] = f"Crony: {subject}"

            # Plain text fallback
            full_body = f"Job: {job_name}\n\n{body}"
            if include_logs and log_content:
                full_body += f"\n\n--- Logs ---\n{log_content[:2000]}"
            part1 = MIMEText(full_body, 'plain')

            # HTML version
            color = "#10B981" if is_success else "#EF4444"
            status_text = "Success" if is_success else "Failed"
            
            html_content = f"""
            <html>
                <head>
                    <style>
                        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; line-height: 1.6; color: #333; margin: 0; padding: 0; background-color: #f4f4f5; }}
                        .container {{ max-width: 600px; margin: 20px auto; padding: 30px; background-color: #ffffff; border-radius: 12px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1); }}
                        .header {{ border-bottom: 2px solid {color}; padding-bottom: 15px; margin-bottom: 25px; display: flex; align-items: center; justify-content: space-between; }}
                        .header h2 {{ margin: 0; font-size: 24px; color: #111827; }}
                        .status-badge {{ background-color: {color}; color: white; padding: 4px 12px; border-radius: 9999px; font-size: 14px; font-weight: 600; }}
                        .content {{ background: #f9fafb; padding: 20px; border-radius: 8px; margin-bottom: 25px; border: 1px solid #e5e7eb; }}
                        .content p {{ margin: 8px 0; font-size: 16px; }}
                        .logs-container {{ margin-top: 20px; }}
                        .logs-title {{ font-size: 18px; font-weight: 600; margin-bottom: 10px; color: #374151; }}
                        .logs {{ background: #1f2937; color: #d1d5db; padding: 16px; border-radius: 8px; font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, Courier, monospace; white-space: pre-wrap; font-size: 13px; overflow-x: auto; line-height: 1.5; }}
                        .footer {{ margin-top: 30px; font-size: 13px; color: #9ca3af; text-align: center; border-top: 1px solid #f3f4f6; padding-top: 20px; }}
                    </style>
                </head>
                <body>
                    <div class="container">
                        <div class="header">
                            <h2>Crony</h2>
                            <span class="status-badge">{status_text}</span>
                        </div>
                        
                        <div class="content">
                            <p><strong>Job Name:</strong> {job_name}</p>
                            <p><strong>Status Message:</strong> {body}</p>
                        </div>
            """
            
            if include_logs and log_content:
                # Escape minimal HTML in logs (not comprehensive, but prevents basic tags from breaking)
                safe_logs = log_content[:4000].replace('<', '&lt;').replace('>', '&gt;')
                html_content += f"""
                        <div class="logs-container">
                            <div class="logs-title">Execution Logs</div>
                            <div class="logs">{safe_logs}</div>
                        </div>
                """
                
            html_content += """
                        <div class="footer">
                            <p>Sent automatically by Crony local daemon</p>
                        </div>
                    </div>
                </body>
            </html>
            """
            
            part2 = MIMEText(html_content, 'html')

            # Attach parts into message container
            msg.attach(part1)
            msg.attach(part2)

            # Send
            server = smtplib.SMTP(self.server, self.port)
            if self.use_tls:
                server.starttls()
            server.login(self.username, self.password)
            text = msg.as_string()
            server.sendmail(self.username, self.recipients, text)
            server.quit()

            LOG.info(f"Email notification sent to {len(self.recipients)} recipients")

        except Exception as e:
            LOG.error(f"Failed to send email notification: {e}")
            raise  # Re-raise para que el llamador sepa que falló

def notify_job_completion(email_config: Dict, job_name: str, success: bool,
                         duration: float, stdout: str = "", stderr: str = "",
                         notify_config: Dict = None):
    """Send email notification for job completion."""
    if not email_config or not email_config.get('enabled', False):
        return

    t = get_translator()
    notifier = EmailNotifier(email_config)
    if not notifier.enabled:
        return

    # Determine if we should send notification and whether to include logs
    if notify_config is not None:
        # Job-specific config: check on_success/on_failure with default True
        should_notify = (success and notify_config.get('on_success', True)) or \
                       (not success and notify_config.get('on_failure', True))
        if not should_notify:
            return
        include_logs = notify_config.get('include_logs', False)
    else:
        # Use global config: check notify_on settings
        notify_on = email_config.get('notify_on', {})
        should_notify = (success and notify_on.get('success', True)) or \
                       (not success and notify_on.get('failure', True))
        if not should_notify:
            return
        include_logs = True  # Default for jobs without specific config

    if success:
        subject = f"{t('messages.task_created')}: '{job_name}' completed"
        body = f"Task executed successfully in {duration:.1f} seconds."
    else:
        subject = f"Crony: task '{job_name}' failed"
        body = f"Task failed after {duration:.1f} seconds."
        include_logs = True  # Always include logs for failures

    log_content = ""
    if include_logs:
        if stdout:
            log_content += f"STDOUT:\n{stdout}\n\n"
        if stderr:
            log_content += f"STDERR:\n{stderr}"

    notifier.send_notification(subject, body, job_name, include_logs, log_content, is_success=success)