"""
Utility functions for Sales Desk
"""

import os
import yaml
import logging
import time
from typing import Dict, List, Any, Optional, TypedDict
from functools import wraps
from datetime import datetime
import json
import requests

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
        data = yaml.safe_load(f)
        return data if isinstance(data, dict) else {}

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
            
            if last_exception is not None:
                raise last_exception
            raise RuntimeError("Operation failed with no exception captured")
        
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

class MetricsData(TypedDict):
    total_requests: int
    approved_requests: int
    denied_requests: int
    escalations: int
    artifacts_shared: Dict[str, int]
    response_times: List[float]
    error_count: int


class MetricsCollector:
    """Collect metrics for monitoring and analytics"""
    
    def __init__(self):
        self.metrics: MetricsData = MetricsData(
            total_requests=0,
            approved_requests=0,
            denied_requests=0,
            escalations=0,
            artifacts_shared={},
            response_times=[],
            error_count=0,
        )
    
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
            self.metrics['artifacts_shared'][artifact] = (
                self.metrics['artifacts_shared'].get(artifact, 0) + 1
            )
        
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


def post_slack_message(webhook_url: str, text: str, blocks: Optional[List[Dict[str, Any]]] = None) -> bool:
    """Post a message to Slack via incoming webhook.

    Returns True on success, False otherwise. Never raises.
    """
    try:
        payload: Dict[str, Any] = {"text": text}
        if blocks:
            payload["blocks"] = blocks
        resp = requests.post(webhook_url, json=payload, timeout=5)
        return 200 <= resp.status_code < 300
    except Exception:
        logging.getLogger('sales_desk').warning("Slack post failed (ignored)")
        return False


def notify_escalation(config: Dict[str, Any], email_from: str, reason: str, details: Dict[str, Any]) -> None:
    """Notify escalation via Slack if enabled.

    Uses settings.notifications.slack.enabled and webhook_url or SLACK_WEBHOOK_URL env.
    """
    try:
        notif = (config.get("settings", {}).get("notifications", {}) or {})
        slack_cfg = (notif.get("slack") or {})
        enabled = bool(slack_cfg.get("enabled", False))
        webhook_url = os.getenv("SLACK_WEBHOOK_URL") or slack_cfg.get("webhook_url")
        if enabled and webhook_url:
            text = f"Escalation: {reason}\nFrom: {email_from}\nDetails: {json.dumps(details)[:500]}"
            post_slack_message(webhook_url, text)
    except Exception:
        logging.getLogger('sales_desk').warning("notify_escalation failed (ignored)")


# Persistence for webhook idempotency and history tracking

class StateStore:
    """Interface for storing webhook processing state."""

    def get_last_history_id(self) -> Optional[str]:
        raise NotImplementedError

    def set_last_history_id(self, history_id: str) -> None:
        raise NotImplementedError

    def is_processed_history(self, history_id: str) -> bool:
        raise NotImplementedError

    def mark_processed_history(self, history_id: str) -> None:
        raise NotImplementedError

    def is_processed_message(self, message_id: str) -> bool:
        raise NotImplementedError

    def mark_processed_message(self, message_id: str) -> None:
        raise NotImplementedError


class MemoryStateStore(StateStore):
    def __init__(self):
        self._last_history_id: Optional[str] = None
        self._processed_history: set[str] = set()
        self._processed_messages: set[str] = set()

    def get_last_history_id(self) -> Optional[str]:
        return self._last_history_id

    def set_last_history_id(self, history_id: str) -> None:
        self._last_history_id = history_id

    def is_processed_history(self, history_id: str) -> bool:
        return history_id in self._processed_history

    def mark_processed_history(self, history_id: str) -> None:
        self._processed_history.add(history_id)

    def is_processed_message(self, message_id: str) -> bool:
        return message_id in self._processed_messages

    def mark_processed_message(self, message_id: str) -> None:
        self._processed_messages.add(message_id)


class RedisStateStore(StateStore):
    def __init__(self, url: str, ttl_days: int = 7, namespace: str = "salesdesk"):
        try:
            import redis  # type: ignore
        except Exception as e:
            raise RuntimeError("redis is not installed. Install requirements-full.txt") from e
        self.redis = redis.Redis.from_url(url)
        self.ttl_seconds = int(ttl_days * 24 * 3600)
        self.ns = namespace

    def _key(self, kind: str, ident: str) -> str:
        return f"{self.ns}:{kind}:{ident}"

    def get_last_history_id(self) -> Optional[str]:
        val: Any = self.redis.get(self._key("last_history_id", "value"))
        if val is None:
            return None
        try:
            # pyrefly: ignore  # missing-attribute
            return val.decode()  # bytes -> str
        except Exception:
            return str(val)

    def set_last_history_id(self, history_id: str) -> None:
        self.redis.set(self._key("last_history_id", "value"), history_id)

    def is_processed_history(self, history_id: str) -> bool:
        return self.redis.exists(self._key("processed_history", history_id)) == 1

    def mark_processed_history(self, history_id: str) -> None:
        self.redis.set(self._key("processed_history", history_id), "1", ex=self.ttl_seconds)

    def is_processed_message(self, message_id: str) -> bool:
        return self.redis.exists(self._key("processed_message", message_id)) == 1

    def mark_processed_message(self, message_id: str) -> None:
        self.redis.set(self._key("processed_message", message_id), "1", ex=self.ttl_seconds)


class PostgresStateStore(StateStore):
    def __init__(self, dsn: str):
        try:
            import psycopg2  # type: ignore
        except Exception as e:
            raise RuntimeError("psycopg2-binary is not installed. Install requirements-full.txt") from e
        self.psycopg2 = psycopg2
        self.dsn = dsn
        self._ensure_tables()

    def _conn(self):
        return self.psycopg2.connect(self.dsn)

    def _ensure_tables(self):
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS webhook_state (
                    id SMALLINT PRIMARY KEY DEFAULT 1,
                    last_history_id TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS processed_events (
                    id TEXT PRIMARY KEY,
                    type TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            conn.commit()

    def get_last_history_id(self) -> Optional[str]:
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT last_history_id FROM webhook_state WHERE id=1")
            row = cur.fetchone()
            return row[0] if row and row[0] else None

    def set_last_history_id(self, history_id: str) -> None:
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO webhook_state (id, last_history_id) VALUES (1, %s)\n"
                "ON CONFLICT (id) DO UPDATE SET last_history_id=EXCLUDED.last_history_id, updated_at=CURRENT_TIMESTAMP",
                (history_id,),
            )
            conn.commit()

    def _is_processed(self, ident: str) -> bool:
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1 FROM processed_events WHERE id=%s", (ident,))
            return cur.fetchone() is not None

    def _mark_processed(self, ident: str, typ: str) -> None:
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO processed_events (id, type) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                (ident, typ),
            )
            conn.commit()

    def is_processed_history(self, history_id: str) -> bool:
        return self._is_processed(f"history:{history_id}")

    def mark_processed_history(self, history_id: str) -> None:
        self._mark_processed(f"history:{history_id}", "history")

    def is_processed_message(self, message_id: str) -> bool:
        return self._is_processed(f"message:{message_id}")

    def mark_processed_message(self, message_id: str) -> None:
        self._mark_processed(f"message:{message_id}", "message")


def get_state_store(config: Dict[str, Any]) -> StateStore:
    """Factory for StateStore based on config settings.persistence."""
    settings = config.get("settings", {})
    p = (settings.get("persistence") or {})
    backend = (p.get("backend") or os.getenv("PERSISTENCE_BACKEND") or "memory").lower()
    if backend == "redis":
        url = p.get("redis_url") or os.getenv("REDIS_URL") or "redis://localhost:6379/0"
        ttl_days = int(p.get("ttl_days", 7))
        return RedisStateStore(url=url, ttl_days=ttl_days)
    if backend == "postgres":
        dsn = os.getenv("DATABASE_URL") or p.get("database_url")
        if not dsn:
            raise RuntimeError("DATABASE_URL not set for Postgres persistence")
        return PostgresStateStore(dsn)
    # Default
    return MemoryStateStore()


def get_bool_setting(config: Dict[str, Any], path: List[str], env_var: Optional[str], default: bool) -> bool:
    """Resolve a boolean setting with optional environment variable override.

    - path: list to traverse under config (e.g., ["settings", "dry_run"]).
    - env_var: if set and present in environment, that value wins (truthy strings like '1','true','yes').
    - default: fallback if not found.
    """
    # Env override
    if env_var:
        val = os.getenv(env_var)
        if val is not None:
            return str(val).strip().lower() in {"1", "true", "t", "yes", "y", "on"}
    # Config path
    cur: Any = config
    try:
        for p in path:
            if isinstance(cur, dict) and p in cur:
                cur = cur[p]
            else:
                return default
        return bool(cur)
    except Exception:
        return default
