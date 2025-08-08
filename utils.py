"""
Utility functions for Sales Desk
"""

import os
import yaml
import logging
import time
from typing import Dict, List, Any, Optional
from functools import wraps
from datetime import datetime
import json

def setup_logging(config_path: str = "config.yaml") -> logging.Logger:
    """Setup logging configuration from config file"""
    config = load_config(config_path)
    log_config = config.get('settings', {}).get('logging', {})
    
    logging.basicConfig(
        level=getattr(logging, log_config.get('level', 'INFO')),
        format=log_config.get('format', '%(asctime)s - %(name)s - %(levelname)s - %(message)s'),
        handlers=[
            logging.FileHandler(log_config.get('file', 'sales_desk.log')),
            logging.StreamHandler()
        ]
    )
    
    return logging.getLogger('sales_desk')

def load_config(config_path: str = "config.yaml") -> Dict:
    """Load configuration from YAML file"""
    if not os.path.exists(config_path):
        # Return default config if file doesn't exist
        return {
            'artifacts': {},
            'nda_database': [],
            'templates': {},
            'settings': {
                'link_expiration_days': 7,
                'email_signature': 'Sales Desk Team',
                'company_name': 'Your Company',
                'monitoring': {
                    'check_interval': 60,
                    'max_per_cycle': 10
                },
                'escalation': {
                    'human_review_keywords': ['legal', 'contract'],
                    'max_sensitive_without_nda': 2
                },
                'logging': {
                    'level': 'INFO',
                    'file': 'sales_desk.log'
                }
            }
        }
    
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)

def retry_with_backoff(max_retries: int = 3, initial_delay: float = 1.0, backoff_factor: float = 2.0):
    """Decorator for retrying functions with exponential backoff"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            delay = initial_delay
            last_exception = None
            
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        logging.warning(f"Attempt {attempt + 1} failed: {e}. Retrying in {delay} seconds...")
                        time.sleep(delay)
                        delay *= backoff_factor
                    else:
                        logging.error(f"All {max_retries} attempts failed. Last error: {e}")
            
            raise last_exception
        
        return wrapper
    return decorator

class AuditLogger:
    """Log all document access and sharing for compliance"""
    
    def __init__(self, log_file: str = "audit.log"):
        self.log_file = log_file
        self.logger = logging.getLogger('audit')
        handler = logging.FileHandler(log_file)
        handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(message)s'
        ))
        self.logger.addHandler(handler)
        self.logger.setLevel(logging.INFO)
    
    def log_request(self, email_from: str, artifacts_requested: List[str], 
                   artifacts_approved: List[str], artifacts_denied: List[str]):
        """Log a document request"""
        self.logger.info(json.dumps({
            'event': 'document_request',
            'timestamp': datetime.now().isoformat(),
            'requester': email_from,
            'requested': artifacts_requested,
            'approved': artifacts_approved,
            'denied': artifacts_denied
        }))
    
    def log_document_sent(self, email_to: str, artifacts: List[str], 
                         method: str, expiration: Optional[str] = None):
        """Log when documents are sent"""
        self.logger.info(json.dumps({
            'event': 'document_sent',
            'timestamp': datetime.now().isoformat(),
            'recipient': email_to,
            'artifacts': artifacts,
            'method': method,
            'expiration': expiration
        }))
    
    def log_escalation(self, email_from: str, reason: str):
        """Log when request is escalated to human"""
        self.logger.info(json.dumps({
            'event': 'escalation',
            'timestamp': datetime.now().isoformat(),
            'requester': email_from,
            'reason': reason
        }))

class MetricsCollector:
    """Collect metrics for monitoring and analytics"""
    
    def __init__(self):
        self.metrics = {
            'total_requests': 0,
            'approved_requests': 0,
            'denied_requests': 0,
            'escalations': 0,
            'artifacts_shared': {},
            'response_times': [],
            'error_count': 0
        }
    
    def record_request(self, approved: bool, escalated: bool, 
                      artifacts: List[str], response_time: float):
        """Record metrics for a request"""
        self.metrics['total_requests'] += 1
        
        if approved:
            self.metrics['approved_requests'] += 1
        else:
            self.metrics['denied_requests'] += 1
        
        if escalated:
            self.metrics['escalations'] += 1
        
        for artifact in artifacts:
            self.metrics['artifacts_shared'][artifact] = \
                self.metrics['artifacts_shared'].get(artifact, 0) + 1
        
        self.metrics['response_times'].append(response_time)
    
    def record_error(self):
        """Record an error occurrence"""
        self.metrics['error_count'] += 1
    
    def get_summary(self) -> Dict:
        """Get metrics summary"""
        avg_response_time = (
            sum(self.metrics['response_times']) / len(self.metrics['response_times'])
            if self.metrics['response_times'] else 0
        )
        
        return {
            'total_requests': self.metrics['total_requests'],
            'approval_rate': (
                self.metrics['approved_requests'] / self.metrics['total_requests'] * 100
                if self.metrics['total_requests'] > 0 else 0
            ),
            'escalation_rate': (
                self.metrics['escalations'] / self.metrics['total_requests'] * 100
                if self.metrics['total_requests'] > 0 else 0
            ),
            'avg_response_time': avg_response_time,
            'top_artifacts': sorted(
                self.metrics['artifacts_shared'].items(),
                key=lambda x: x[1],
                reverse=True
            )[:5],
            'error_count': self.metrics['error_count']
        }

def validate_email(email: str) -> bool:
    """Basic email validation"""
    import re
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def sanitize_filename(filename: str) -> str:
    """Sanitize filename to prevent path traversal"""
    import re
    # Remove any path components
    filename = os.path.basename(filename)
    # Remove special characters
    filename = re.sub(r'[^\w\s.-]', '', filename)
    return filename

def generate_secure_link(artifact_id: str, recipient: str, expiration_days: int = 7) -> str:
    """Generate a secure, expiring link for document access"""
    import hashlib
    import base64
    from datetime import timedelta
    
    # In production, this would generate actual secure links
    # For now, create a mock secure link
    expiration = datetime.now() + timedelta(days=expiration_days)
    
    # Create a hash of artifact + recipient + expiration
    hash_input = f"{artifact_id}:{recipient}:{expiration.isoformat()}"
    hash_value = hashlib.sha256(hash_input.encode()).digest()
    token = base64.urlsafe_b64encode(hash_value).decode()[:32]
    
    return f"https://secure.yourcompany.com/docs/{token}"