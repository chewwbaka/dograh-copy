from datetime import UTC, datetime

from loguru import logger
from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    UniqueConstraint,
    and_,
    text,
)
from sqlalchemy.orm import declarative_base, relationship

from ..enums import IntegrationAction, WorkflowRunMode, WorkflowStatus

Base = declarative_base()


# TODO: remove workflow_defintion after migration, remove nullable workflow_defintion_id from Workflow and Workflowrun


# Association table for many-to-many relationship between users and organizations
organization_users_association = Table(
    "organization_users",
    Base.metadata,
    Column("user_id", Integer, ForeignKey("users.id"), primary_key=True),
    Column(
        "organization_id", Integer, ForeignKey("organizations.id"), primary_key=True
    ),
)


class UserModel(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    provider_id = Column(String, unique=True, index=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    workflows = relationship("WorkflowModel", back_populates="user")
    selected_organization_id = Column(
        Integer, ForeignKey("organizations.id"), nullable=True
    )
    selected_organization = relationship("OrganizationModel", back_populates="users")
    organizations = relationship(
        "OrganizationModel",
        secondary=organization_users_association,
        back_populates="users",
    )
    is_superuser = Column(Boolean, default=False)


class UserConfigurationModel(Base):
    __tablename__ = "user_configurations"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    configuration = Column(JSON, nullable=False, default=dict)
    last_validated_at = Column(DateTime(timezone=True), nullable=True)


# New Organization model
class OrganizationModel(Base):
    __tablename__ = "organizations"

    id = Column(Integer, primary_key=True, index=True)
    provider_id = Column(String, unique=True, index=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    # Quota fields
    quota_type = Column(
        Enum("monthly", "annual", name="quota_type"),
        nullable=False,
        default="monthly",
        server_default=text("'monthly'::quota_type"),
    )
    quota_dograh_tokens = Column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    quota_reset_day = Column(
        Integer, nullable=False, default=1, server_default=text("1")
    )  # 1-28, only for monthly
    quota_start_date = Column(DateTime(timezone=True), nullable=True)  # Only for annual
    quota_enabled = Column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )

    price_per_second_usd = Column(Float, nullable=True)

    # Relationships
    users = relationship(
        "UserModel",
        secondary=organization_users_association,
        back_populates="organizations",
    )
    integrations = relationship("IntegrationModel", back_populates="organization")
    usage_cycles = relationship(
        "OrganizationUsageCycleModel", back_populates="organization"
    )
    configurations = relationship(
        "OrganizationConfigurationModel", back_populates="organization"
    )
    api_keys = relationship("APIKeyModel", back_populates="organization")


class APIKeyModel(Base):
    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(
        Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    name = Column(String, nullable=False)
    key_hash = Column(String, nullable=False, unique=True, index=True)
    key_prefix = Column(String, nullable=False)  # Store first 8 chars for display
    is_active = Column(Boolean, default=True, nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    archived_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    organization = relationship("OrganizationModel", back_populates="api_keys")
    created_by_user = relationship("UserModel")

    # Indexes for performance
    __table_args__ = (
        Index("ix_api_keys_organization_id", "organization_id"),
        Index("ix_api_keys_key_hash", "key_hash"),
        Index("ix_api_keys_active", "is_active"),
    )


class OrganizationConfigurationModel(Base):
    __tablename__ = "organization_configurations"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(
        Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    key = Column(String, nullable=False)
    value = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    # Relationships
    organization = relationship("OrganizationModel", back_populates="configurations")

    # Constraints and indexes
    __table_args__ = (
        UniqueConstraint("organization_id", "key", name="_organization_key_uc"),
        Index("ix_organization_configurations_organization_id", "organization_id"),
    )


class IntegrationModel(Base):
    __tablename__ = "integrations"

    id = Column(Integer, primary_key=True, index=True)
    integration_id = Column(String, nullable=False, index=True)  # Nango Connection ID
    organisation_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    provider = Column(String, nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"))
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    connection_details = Column(JSON, nullable=False, default=dict)
    action = Column(String, nullable=False, default=IntegrationAction.ALL_CALLS.value)

    # Relationships
    organization = relationship("OrganizationModel", back_populates="integrations")


class WorkflowDefinitionModel(Base):
    __tablename__ = "workflow_definitions"
    id = Column(Integer, primary_key=True, index=True)
    workflow_hash = Column(String, nullable=False)
    workflow_json = Column(JSON, nullable=False, default=dict)
    workflow_id = Column(Integer, ForeignKey("workflows.id"), nullable=True)
    is_current = Column(
        Boolean, default=False, nullable=False, server_default=text("false")
    )
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    # Table constraints and indexes
    __table_args__ = (
        UniqueConstraint(
            "workflow_hash", "workflow_id", name="uq_workflow_hash_workflow_id"
        ),
        Index("ix_workflow_hash_workflow_id", "workflow_hash", "workflow_id"),
    )

    # Relationships
    workflow = relationship(
        "WorkflowModel",
        back_populates="definitions",
        foreign_keys=[workflow_id],
    )
    workflow_runs = relationship("WorkflowRunModel", back_populates="definition")


class WorkflowModel(Base):
    __tablename__ = "workflows"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    user = relationship("UserModel", back_populates="workflows")
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True)
    organization = relationship("OrganizationModel")
    name = Column(String, index=True, nullable=False)
    status = Column(
        Enum(*[status.value for status in WorkflowStatus], name="workflow_status"),
        nullable=False,
        default=WorkflowStatus.ACTIVE.value,
        server_default=text("'active'::workflow_status"),
    )
    workflow_definition = Column(JSON, nullable=False, default=dict)
    template_context_variables = Column(JSON, nullable=False, default=dict)
    call_disposition_codes = Column(JSON, nullable=False, default=dict)
    workflow_configurations = Column(
        JSON, nullable=False, default=dict, server_default=text("'{}'::json")
    )
    runs = relationship("WorkflowRunModel", back_populates="workflow")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    # All versions / historical definitions of this workflow
    definitions = relationship(
        "WorkflowDefinitionModel",
        back_populates="workflow",
        foreign_keys="WorkflowDefinitionModel.workflow_id",
    )

    # Relationship to fetch the current (is_current=True) definition
    current_definition = relationship(
        "WorkflowDefinitionModel",
        primaryjoin=lambda: and_(
            WorkflowDefinitionModel.workflow_id == WorkflowModel.id,
            WorkflowDefinitionModel.is_current.is_(True),
        ),
        uselist=False,
        viewonly=True,
    )

    @property
    def current_definition_id(self):
        """Return ID of the current workflow definition (helper for backwards-compat)."""
        current_def = self.__dict__.get("current_definition")
        if current_def is not None:
            return current_def.id

        # If relationship is not loaded, we cannot safely access definitions without
        # risking an implicit lazy load on a detached instance. Return ``None`` in
        # that scenario so callers can handle the absence explicitly.
        return None

    @property
    def workflow_definition_with_fallback(self):
        """
        Get workflow definition with fallback to legacy workflow_definition field.

        Returns:
            dict: The workflow definition JSON
        """
        # Access the relationship only if it has ALREADY been eagerly loaded on this
        # instance to avoid triggering an implicit lazy load once the SQLAlchemy
        # Session has been closed (which would raise a DetachedInstanceError).

        # ``__dict__`` will contain "current_definition" **only** when the attribute
        # has been populated (e.g. via `selectinload` or an explicit access while
        # the session was still open). Using ``__dict__.get`` guarantees that we
        # do not accidentally issue a lazy load query on a detached instance.

        current_definition = self.__dict__.get("current_definition")

        if current_definition is not None:
            return current_definition.workflow_json

        # Fallback for backwards-compatibility when the relationship is not (yet)
        # loaded. In this case we fall back to the legacy ``workflow_definition``
        # column that always contains the most recent definition JSON.
        logger.warning(
            f"Workflow {self.id} has no loaded current definition, using workflow_definition as fallback",
        )
        return self.workflow_definition


class WorkflowTemplates(Base):
    __tablename__ = "workflow_templates"
    id = Column(Integer, primary_key=True, index=True)
    template_name = Column(String, nullable=False, index=True)
    template_description = Column(String, nullable=False, index=True)
    template_json = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class WorkflowRunModel(Base):
    __tablename__ = "workflow_runs"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    workflow_id = Column(Integer, ForeignKey("workflows.id"), nullable=False)
    workflow = relationship("WorkflowModel", back_populates="runs")
    definition_id = Column(
        Integer, ForeignKey("workflow_definitions.id"), nullable=True
    )
    definition = relationship("WorkflowDefinitionModel", back_populates="workflow_runs")
    mode = Column(
        Enum(*[mode.value for mode in WorkflowRunMode], name="workflow_run_mode"),
        nullable=False,
    )
    is_completed = Column(Boolean, default=False)
    recording_url = Column(String, nullable=True)
    transcript_url = Column(String, nullable=True)
    # Store storage backend as string enum (s3, minio)
    storage_backend = Column(
        Enum("s3", "minio", name="storage_backend"),
        nullable=False,
        default="s3",
        server_default=text("'s3'::storage_backend"),
    )
    usage_info = Column(JSON, nullable=False, default=dict)
    cost_info = Column(JSON, nullable=False, default=dict)
    initial_context = Column(JSON, nullable=False, default=dict)
    gathered_context = Column(JSON, nullable=False, default=dict)
    logs = Column(JSON, nullable=False, default=dict, server_default=text("'{}'::json"))
    annotations = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    campaign_id = Column(Integer, ForeignKey("campaigns.id"), nullable=True)
    campaign = relationship("CampaignModel")
    queued_run_id = Column(Integer, ForeignKey("queued_runs.id"), nullable=True)
    queued_run = relationship("QueuedRunModel", foreign_keys=[queued_run_id])


# LoopTalk Testing Models
class LoopTalkTestSession(Base):
    __tablename__ = "looptalk_test_sessions"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    name = Column(String, nullable=False)
    status = Column(
        Enum("pending", "running", "completed", "failed", name="test_session_status"),
        nullable=False,
        default="pending",
    )

    # Workflow configuration
    actor_workflow_id = Column(Integer, ForeignKey("workflows.id"), nullable=False)
    adversary_workflow_id = Column(Integer, ForeignKey("workflows.id"), nullable=False)

    # Load testing configuration
    load_test_group_id = Column(String, nullable=True, index=True)
    test_index = Column(Integer, nullable=True)

    # Test metadata
    config = Column(JSON, nullable=False, default=dict)
    results = Column(JSON, nullable=False, default=dict)
    error = Column(String, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    organization = relationship("OrganizationModel")
    actor_workflow = relationship("WorkflowModel", foreign_keys=[actor_workflow_id])
    adversary_workflow = relationship(
        "WorkflowModel", foreign_keys=[adversary_workflow_id]
    )
    conversations = relationship("LoopTalkConversation", back_populates="test_session")

    # Indexes for performance
    __table_args__ = (
        Index("ix_looptalk_test_sessions_org_id", "organization_id"),
        Index("ix_looptalk_test_sessions_group_id", "load_test_group_id"),
        Index("ix_looptalk_test_sessions_status", "status"),
    )


class LoopTalkConversation(Base):
    __tablename__ = "looptalk_conversations"

    id = Column(Integer, primary_key=True, index=True)
    test_session_id = Column(
        Integer, ForeignKey("looptalk_test_sessions.id"), nullable=False
    )

    # Conversation metadata
    duration_seconds = Column(Integer, nullable=True)
    # Note: Turn tracking is handled by Langfuse, not stored here

    # Audio recording URLs
    actor_recording_url = Column(String, nullable=True)
    adversary_recording_url = Column(String, nullable=True)
    combined_recording_url = Column(String, nullable=True)

    # Transcripts (if needed for quick access)
    transcript = Column(JSON, nullable=False, default=dict)

    # Metrics
    metrics = Column(JSON, nullable=False, default=dict)

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    ended_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    test_session = relationship("LoopTalkTestSession", back_populates="conversations")

    # Indexes
    __table_args__ = (Index("ix_looptalk_conversations_session_id", "test_session_id"),)


class OrganizationUsageCycleModel(Base):
    """
    This model is used to track the usage of Dograh tokens for an organization for a given usage
    cycle.
    """

    __tablename__ = "organization_usage_cycles"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    period_start = Column(DateTime(timezone=True), nullable=False)
    period_end = Column(DateTime(timezone=True), nullable=False)
    quota_dograh_tokens = Column(Integer, nullable=False)
    used_dograh_tokens = Column(Float, nullable=False, default=0)
    total_duration_seconds = Column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    # New USD tracking fields
    used_amount_usd = Column(Float, nullable=True, default=0)
    quota_amount_usd = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    # Relationships
    organization = relationship("OrganizationModel", back_populates="usage_cycles")

    # Constraints and indexes
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "period_start", "period_end", name="unique_org_period"
        ),
        Index("idx_usage_cycles_org_period", "organization_id", "period_end"),
    )


class CampaignModel(Base):
    __tablename__ = "campaigns"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    workflow_id = Column(Integer, ForeignKey("workflows.id"), nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)

    # Source configuration
    source_type = Column(String, nullable=False, default="google-sheet")
    source_id = Column(String, nullable=False)  # Sheet URL

    # State management
    state = Column(
        Enum(
            "created",
            "syncing",
            "running",
            "paused",
            "completed",
            "failed",
            name="campaign_state",
        ),
        nullable=False,
        default="created",
    )

    # Progress tracking
    total_rows = Column(Integer, nullable=True)
    processed_rows = Column(Integer, nullable=False, default=0)
    failed_rows = Column(Integer, nullable=False, default=0)

    # Rate limiting and sync configuration
    rate_limit_per_second = Column(Integer, nullable=False, default=1)
    max_retries = Column(Integer, nullable=False, default=0)
    source_sync_status = Column(String, nullable=False, default="pending")
    source_last_synced_at = Column(DateTime(timezone=True), nullable=True)
    source_sync_error = Column(String, nullable=True)

    # Retry configuration for call failures
    retry_config = Column(
        JSON,
        nullable=False,
        default={
            "enabled": True,
            "max_retries": 2,
            "retry_delay_seconds": 120,
            "retry_on_busy": True,
            "retry_on_no_answer": True,
            "retry_on_voicemail": True,
        },
        server_default=text(
            '\'{"enabled": true, "max_retries": 2, "retry_on_busy": true, "retry_on_no_answer": true, "retry_on_voicemail": true, "retry_delay_seconds": 120}\'::jsonb'
        ),
    )

    # Orchestrator tracking fields
    last_batch_scheduled_at = Column(DateTime(timezone=True), nullable=True)
    last_activity_at = Column(DateTime(timezone=True), nullable=True)
    orchestrator_metadata = Column(
        JSON, nullable=False, default=dict, server_default=text("'{}'::json")
    )

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    # Relationships
    organization = relationship("OrganizationModel")
    workflow = relationship("WorkflowModel")
    created_by_user = relationship("UserModel")

    # Indexes
    __table_args__ = (
        Index("ix_campaigns_org_id", "organization_id"),
        Index("ix_campaigns_state", "state"),
        Index("ix_campaigns_workflow_id", "workflow_id"),
        # Index for efficient querying of active campaigns
        Index(
            "idx_campaigns_active_status",
            "state",
            postgresql_where=text("state IN ('syncing', 'running', 'paused')"),
        ),
    )


class QueuedRunModel(Base):
    __tablename__ = "queued_runs"

    id = Column(Integer, primary_key=True, index=True)
    campaign_id = Column(
        Integer, ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False
    )
    source_uuid = Column(String, nullable=False)
    context_variables = Column(JSON, nullable=False, default=dict)
    state = Column(
        Enum("queued", "processed", "failed", name="queued_run_state"),
        nullable=False,
        default="queued",
    )
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    processed_at = Column(DateTime(timezone=True), nullable=True)

    # New retry-related fields
    retry_count = Column(Integer, default=0, nullable=False, server_default=text("0"))
    parent_queued_run_id = Column(Integer, ForeignKey("queued_runs.id"), nullable=True)
    scheduled_for = Column(DateTime(timezone=True), nullable=True)
    retry_reason = Column(String, nullable=True)  # 'busy', 'no_answer', 'voicemail'

    # Relationships
    campaign = relationship("CampaignModel")
    parent_queued_run = relationship("QueuedRunModel", remote_side=[id])

    # Indexes
    __table_args__ = (
        Index("idx_queued_runs_campaign_state", "campaign_id", "state"),
        Index("idx_queued_runs_created", "created_at"),
        Index("idx_queued_runs_source_uuid", "source_uuid"),
        Index(
            "idx_queued_runs_scheduled", "scheduled_for"
        ),  # New index for scheduled retries
        # Optimized index for checking queued runs efficiently
        Index(
            "idx_queued_runs_campaign_state_optimized",
            "campaign_id",
            "state",
            postgresql_where=text("state = 'queued'"),
        ),
        # Optimized index for scheduled retries
        Index(
            "idx_queued_runs_scheduled_optimized",
            "campaign_id",
            "scheduled_for",
            postgresql_where=text("scheduled_for IS NOT NULL"),
        ),
        UniqueConstraint(
            "campaign_id",
            "source_uuid",
            "retry_count",
            name="unique_campaign_source_retry",
        ),
    )
