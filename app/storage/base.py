from abc import ABC, abstractmethod
from typing import Optional
from app.models.biometric import BiometricTemplate


class BiometricRepository(ABC):
    """
    Abstract interface for biometric template persistence.
    Decouples domain services from concrete storage mechanisms (Local, SQLite, PostgreSQL + pgvector).
    """

    @abstractmethod
    def save_template(self, template: BiometricTemplate) -> bool:
        """Persists a new or updated biometric template."""
        pass

    @abstractmethod
    def get_templates(self, user_id: str) -> list[BiometricTemplate]:
        """Retrieves all active templates for a given user."""
        pass

    @abstractmethod
    def get_template_by_id(self, template_id: str) -> Optional[BiometricTemplate]:
        """Retrieves a single template by its unique template_id."""
        pass

    @abstractmethod
    def get_all_templates(self) -> list[BiometricTemplate]:
        """Retrieves all active templates in the system."""
        pass

    @abstractmethod
    def delete_template(self, template_id: str) -> bool:
        """Deletes or revokes a template by its template_id."""
        pass

    @abstractmethod
    def delete_templates_by_user(self, user_id: str) -> int:
        """Deletes all templates associated with a user. Returns count deleted."""
        pass

    @abstractmethod
    def count(self) -> int:
        """Returns the total number of active enrolled templates."""
        pass
