"""
Database utilities for Rite Audit System.

Provides SQLite-based storage for claim history and audit trail.
"""
import sqlite3
import json
from datetime import datetime
from typing import List, Dict, Any, Optional
from pathlib import Path


class ClaimDatabase:
    """SQLite database for storing claim review history."""
    
    def __init__(self, db_path: str = "claims.db"):
        """
        Initialize database connection.
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self.conn = None
        self._init_db()
    
    def _init_db(self):
        """Initialize database schema."""
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=10.0)
        self.conn.row_factory = sqlite3.Row
        
        cursor = self.conn.cursor()
        
        # Claims table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS claims (
                id TEXT PRIMARY KEY,
                employee_id TEXT NOT NULL,
                employee_name TEXT,
                submission_date TEXT NOT NULL,
                claim_period_start TEXT,
                claim_period_end TEXT,
                claimed_amount REAL NOT NULL,
                approved_amount REAL,
                decision TEXT,
                decision_reasoning TEXT,
                final_report TEXT,
                status TEXT DEFAULT 'pending',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Expenses table (line items)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                claim_id TEXT NOT NULL,
                category TEXT NOT NULL,
                amount REAL NOT NULL,
                date TEXT,
                description TEXT,
                source_document TEXT,
                is_valid INTEGER DEFAULT 1,
                validation_notes TEXT,
                eligible_amount REAL,
                FOREIGN KEY (claim_id) REFERENCES claims(id)
            )
        """)
        
        # Documents table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                claim_id TEXT NOT NULL,
                document_type TEXT,
                file_path TEXT,
                extracted_text TEXT,
                extracted_data TEXT,
                ocr_confidence REAL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (claim_id) REFERENCES claims(id)
            )
        """)
        
        # Audit log table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                claim_id TEXT NOT NULL,
                action TEXT NOT NULL,
                agent TEXT,
                details TEXT,
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (claim_id) REFERENCES claims(id)
            )
        """)

        # Migrate: add admin review + line_items columns if not present
        existing = {row[1] for row in cursor.execute("PRAGMA table_info(claims)").fetchall()}
        migrations = {
            "admin_status":          "TEXT DEFAULT 'pending_review'",
            "admin_approved_amount": "REAL",
            "admin_reviewed_at":     "TEXT",
            "admin_notes":           "TEXT",
            "line_items_json":       "TEXT",
            "category_eligible_json":"TEXT",
        }
        for col, col_def in migrations.items():
            if col not in existing:
                cursor.execute(f"ALTER TABLE claims ADD COLUMN {col} {col_def}")

        # Indexes for admin dashboard queries
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_claims_admin_status ON claims(admin_status, created_at)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_claims_employee_id  ON claims(employee_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_claims_created_at   ON claims(created_at)")

        self.conn.commit()
    
    def save_full_claim(self, claim_data: Dict[str, Any], line_items: list) -> str:
        """Save a completed claim with all line items for admin review."""
        claim_id = self.save_claim(claim_data)
        cursor = self.conn.cursor()
        cursor.execute(
            "UPDATE claims SET line_items_json=?, category_eligible_json=? WHERE id=?",
            (
                json.dumps(line_items),
                json.dumps(claim_data.get("category_eligible", {})),
                claim_id,
            ),
        )
        self.conn.commit()
        return claim_id

    def save_claim(self, claim_data: Dict[str, Any]) -> str:
        """
        Save a new claim or update existing one.
        
        Args:
            claim_data: Claim state dictionary
            
        Returns:
            Claim ID
        """
        cursor = self.conn.cursor()
        
        claim_id = claim_data.get("claim_id")
        
        # Check if claim exists
        cursor.execute("SELECT id FROM claims WHERE id = ?", (claim_id,))
        exists = cursor.fetchone() is not None
        
        if exists:
            # Update
            cursor.execute("""
                UPDATE claims SET
                    approved_amount = ?,
                    decision = ?,
                    decision_reasoning = ?,
                    final_report = ?,
                    status = ?,
                    updated_at = ?
                WHERE id = ?
            """, (
                claim_data.get("approved_amount"),
                claim_data.get("decision"),
                claim_data.get("decision_reasoning"),
                claim_data.get("final_report"),
                "completed" if claim_data.get("processing_complete") else "processing",
                datetime.now().isoformat(),
                claim_id
            ))
        else:
            # Insert
            cursor.execute("""
                INSERT INTO claims (
                    id, employee_id, employee_name, submission_date,
                    claim_period_start, claim_period_end, claimed_amount,
                    approved_amount, decision, decision_reasoning, final_report, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                claim_id,
                claim_data.get("employee_id"),
                claim_data.get("employee_name"),
                claim_data.get("submission_date"),
                claim_data.get("claim_period_start"),
                claim_data.get("claim_period_end"),
                claim_data.get("claimed_amount"),
                claim_data.get("approved_amount"),
                claim_data.get("decision"),
                claim_data.get("decision_reasoning"),
                claim_data.get("final_report"),
                "pending"
            ))
        
        self.conn.commit()
        return claim_id
    
    def save_expense(self, claim_id: str, expense: Dict[str, Any]) -> int:
        """Save an expense line item."""
        cursor = self.conn.cursor()
        
        cursor.execute("""
            INSERT INTO expenses (
                claim_id, category, amount, date, description,
                source_document, is_valid, validation_notes, eligible_amount
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            claim_id,
            expense.get("category"),
            expense.get("amount"),
            expense.get("date"),
            expense.get("description"),
            expense.get("source_document"),
            1 if expense.get("is_valid", True) else 0,
            expense.get("validation_notes"),
            expense.get("eligible_amount")
        ))
        
        self.conn.commit()
        return cursor.lastrowid
    
    def save_document(
        self,
        claim_id: str,
        document_type: str,
        file_path: str,
        extracted_text: str = None,
        extracted_data: Dict = None,
        ocr_confidence: float = None
    ) -> int:
        """Save document metadata and extracted data."""
        cursor = self.conn.cursor()
        
        cursor.execute("""
            INSERT INTO documents (
                claim_id, document_type, file_path,
                extracted_text, extracted_data, ocr_confidence
            ) VALUES (?, ?, ?, ?, ?, ?)
        """, (
            claim_id,
            document_type,
            file_path,
            extracted_text,
            json.dumps(extracted_data) if extracted_data else None,
            ocr_confidence
        ))
        
        self.conn.commit()
        return cursor.lastrowid
    
    def log_action(
        self,
        claim_id: str,
        action: str,
        agent: str = None,
        details: str = None
    ):
        """Log an action in the audit trail."""
        cursor = self.conn.cursor()
        
        cursor.execute("""
            INSERT INTO audit_log (claim_id, action, agent, details)
            VALUES (?, ?, ?, ?)
        """, (claim_id, action, agent, details))
        
        self.conn.commit()
    
    def get_claim(self, claim_id: str) -> Optional[Dict[str, Any]]:
        """Get a claim by ID."""
        cursor = self.conn.cursor()
        
        cursor.execute("SELECT * FROM claims WHERE id = ?", (claim_id,))
        row = cursor.fetchone()
        
        if row:
            return dict(row)
        return None
    
    def get_claim_expenses(self, claim_id: str) -> List[Dict[str, Any]]:
        """Get all expenses for a claim."""
        cursor = self.conn.cursor()
        
        cursor.execute("SELECT * FROM expenses WHERE claim_id = ?", (claim_id,))
        return [dict(row) for row in cursor.fetchall()]
    
    def get_claim_documents(self, claim_id: str) -> List[Dict[str, Any]]:
        """Get all documents for a claim."""
        cursor = self.conn.cursor()
        
        cursor.execute("SELECT * FROM documents WHERE claim_id = ?", (claim_id,))
        rows = cursor.fetchall()
        
        result = []
        for row in rows:
            doc = dict(row)
            if doc.get("extracted_data"):
                doc["extracted_data"] = json.loads(doc["extracted_data"])
            result.append(doc)
        
        return result
    
    def get_audit_log(self, claim_id: str) -> List[Dict[str, Any]]:
        """Get audit log for a claim."""
        cursor = self.conn.cursor()
        
        cursor.execute(
            "SELECT * FROM audit_log WHERE claim_id = ? ORDER BY timestamp",
            (claim_id,)
        )
        return [dict(row) for row in cursor.fetchall()]
    
    def get_employee_claims(
        self,
        employee_id: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Get recent claims for an employee."""
        cursor = self.conn.cursor()
        
        cursor.execute("""
            SELECT * FROM claims 
            WHERE employee_id = ? 
            ORDER BY created_at DESC 
            LIMIT ?
        """, (employee_id, limit))
        
        return [dict(row) for row in cursor.fetchall()]
    
    def get_pending_claims(self) -> List[Dict[str, Any]]:
        """Get all pending claims."""
        cursor = self.conn.cursor()
        
        cursor.execute("""
            SELECT * FROM claims 
            WHERE status IN ('pending', 'processing')
            ORDER BY created_at
        """)
        
        return [dict(row) for row in cursor.fetchall()]
    
    def get_all_claims(self, status_filter: str = None, limit: int = 10, offset: int = 0) -> List[Dict[str, Any]]:
        """Return paginated claims for the admin dashboard, newest first."""
        cursor = self.conn.cursor()
        if status_filter and status_filter != "all":
            cursor.execute(
                "SELECT * FROM claims WHERE admin_status=? ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (status_filter, limit, offset),
            )
        else:
            cursor.execute(
                "SELECT * FROM claims ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            )
        return [dict(r) for r in cursor.fetchall()]

    def count_claims(self, status_filter: str = None) -> int:
        """Count total claims for pagination."""
        cursor = self.conn.cursor()
        if status_filter and status_filter != "all":
            row = cursor.execute(
                "SELECT COUNT(*) FROM claims WHERE admin_status=?", (status_filter,)
            ).fetchone()
        else:
            row = cursor.execute("SELECT COUNT(*) FROM claims").fetchone()
        return row[0] if row else 0

    def get_claim_stats(self) -> Dict[str, Any]:
        """Summary stats for the dashboard header."""
        cursor = self.conn.cursor()
        row = cursor.execute("""
            SELECT
                COUNT(*)                                        AS total,
                SUM(CASE WHEN admin_status='pending_review' THEN 1 ELSE 0 END) AS pending,
                SUM(claimed_amount)                             AS total_claimed,
                SUM(approved_amount)                           AS total_system_approved,
                SUM(COALESCE(admin_approved_amount, approved_amount)) AS total_final_approved,
                SUM(CASE WHEN admin_approved_amount IS NOT NULL
                          AND ABS(admin_approved_amount - COALESCE(approved_amount, 0)) > 0.5
                     THEN 1 ELSE 0 END)                        AS total_overrides,
                ROUND(AVG(CASE WHEN admin_reviewed_at IS NOT NULL
                               AND submission_date IS NOT NULL
                               THEN julianday(admin_reviewed_at) - julianday(submission_date)
                          END), 1)                             AS avg_review_days
            FROM claims
        """).fetchone()
        return dict(row) if row else {}

    def update_admin_decision(
        self,
        claim_id: str,
        admin_approved_amount: float,
        admin_notes: str = "",
    ) -> None:
        """Persist admin's final decision on a claim."""
        cursor = self.conn.cursor()
        cursor.execute("""
            UPDATE claims
            SET admin_approved_amount=?, admin_status='admin_reviewed',
                admin_reviewed_at=?, admin_notes=?, updated_at=?
            WHERE id=?
        """, (
            admin_approved_amount,
            datetime.now().isoformat(),
            admin_notes,
            datetime.now().isoformat(),
            claim_id,
        ))
        self.conn.commit()

    def get_line_items(self, claim_id: str) -> List[Dict[str, Any]]:
        """Return stored line items for a claim (for admin review)."""
        cursor = self.conn.cursor()
        row = cursor.execute(
            "SELECT line_items_json FROM claims WHERE id=?", (claim_id,)
        ).fetchone()
        if row and row["line_items_json"]:
            return json.loads(row["line_items_json"])
        return []

    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()


# Global database instance
_db_instance: Optional[ClaimDatabase] = None


def get_db(db_path: str = "claims.db") -> ClaimDatabase:
    """Get or create the global database instance."""
    global _db_instance
    if _db_instance is None:
        _db_instance = ClaimDatabase(db_path)
    return _db_instance
