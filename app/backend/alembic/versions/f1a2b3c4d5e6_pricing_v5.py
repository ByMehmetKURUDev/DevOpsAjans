"""fiyatlandirma v5: pricing_scales/profiles/services/addons, ai_pm_tiers, pricing_inquiries

Revision ID: f1a2b3c4d5e6
Revises: a52336dc1593
Create Date: 2026-09-29 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, Sequence[str], None] = 'a52336dc1593'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'pricing_scales',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('kod', sa.String(), nullable=False),
        sa.Column('sira', sa.Integer(), nullable=False),
        sa.Column('ad', sa.String(), nullable=False),
        sa.Column('alt_baslik', sa.String(), nullable=False),
        sa.Column('calisan_araligi', sa.String(), nullable=False),
        sa.Column('aciklama', sa.Text(), nullable=False),
        sa.Column('baz_aylik_fiyat_usd', sa.Float(), nullable=False),
        sa.Column('ozellikler', sa.Text(), nullable=True),
        sa.Column('eklenti_limiti', sa.String(), nullable=True),
        sa.Column('revizyon_saat', sa.String(), nullable=True),
        sa.Column('populer', sa.Boolean(), nullable=True),
        sa.Column('karsilastirma', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_pricing_scales_id'), 'pricing_scales', ['id'], unique=False)
    op.create_index(op.f('ix_pricing_scales_kod'), 'pricing_scales', ['kod'], unique=False)

    op.create_table(
        'pricing_profiles',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('kod', sa.String(), nullable=False),
        sa.Column('ad', sa.String(), nullable=False),
        sa.Column('carpan', sa.Float(), nullable=False),
        sa.Column('etiket', sa.String(), nullable=True),
        sa.Column('sira', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_pricing_profiles_id'), 'pricing_profiles', ['id'], unique=False)
    op.create_index(op.f('ix_pricing_profiles_kod'), 'pricing_profiles', ['kod'], unique=False)

    op.create_table(
        'pricing_services',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('kategori', sa.String(), nullable=False),
        sa.Column('ad', sa.String(), nullable=False),
        sa.Column('baz_fiyat_usd', sa.Float(), nullable=False),
        sa.Column('tek_seferlik', sa.Boolean(), nullable=True),
        sa.Column('not_metni', sa.String(), nullable=True),
        sa.Column('yeni', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_pricing_services_id'), 'pricing_services', ['id'], unique=False)
    op.create_index(op.f('ix_pricing_services_kategori'), 'pricing_services', ['kategori'], unique=False)

    op.create_table(
        'pricing_addons',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('scale_kod', sa.String(), nullable=False),
        sa.Column('ad', sa.String(), nullable=False),
        sa.Column('baz_fiyat_usd', sa.Float(), nullable=False),
        sa.Column('birim', sa.String(), nullable=True),
        sa.Column('sira', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_pricing_addons_id'), 'pricing_addons', ['id'], unique=False)
    op.create_index(op.f('ix_pricing_addons_scale_kod'), 'pricing_addons', ['scale_kod'], unique=False)

    op.create_table(
        'ai_pm_tiers',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('kod', sa.String(), nullable=False),
        sa.Column('ad', sa.String(), nullable=False),
        sa.Column('fiyat_aylik_usd', sa.Float(), nullable=False),
        sa.Column('rozet', sa.String(), nullable=True),
        sa.Column('ozellikler', sa.Text(), nullable=True),
        sa.Column('sira', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_ai_pm_tiers_id'), 'ai_pm_tiers', ['id'], unique=False)
    op.create_index(op.f('ix_ai_pm_tiers_kod'), 'ai_pm_tiers', ['kod'], unique=False)

    op.create_table(
        'pricing_inquiries',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('scale_kod', sa.String(), nullable=True),
        sa.Column('profile_kod', sa.String(), nullable=True),
        sa.Column('ai_pm_tier_kod', sa.String(), nullable=True),
        sa.Column('period', sa.String(), nullable=True),
        sa.Column('addon_ids', sa.Text(), nullable=True),
        sa.Column('hesaplanan_tutar', sa.Float(), nullable=False),
        sa.Column('musteri_eposta', sa.String(), nullable=False),
        sa.Column('musteri_adi', sa.String(), nullable=True),
        sa.Column('kaynak', sa.String(), nullable=True),
        sa.Column('invoice_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['invoice_id'], ['invoices.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_pricing_inquiries_id'), 'pricing_inquiries', ['id'], unique=False)
    op.create_index(op.f('ix_pricing_inquiries_musteri_eposta'), 'pricing_inquiries', ['musteri_eposta'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_pricing_inquiries_musteri_eposta'), table_name='pricing_inquiries')
    op.drop_index(op.f('ix_pricing_inquiries_id'), table_name='pricing_inquiries')
    op.drop_table('pricing_inquiries')

    op.drop_index(op.f('ix_ai_pm_tiers_kod'), table_name='ai_pm_tiers')
    op.drop_index(op.f('ix_ai_pm_tiers_id'), table_name='ai_pm_tiers')
    op.drop_table('ai_pm_tiers')

    op.drop_index(op.f('ix_pricing_addons_scale_kod'), table_name='pricing_addons')
    op.drop_index(op.f('ix_pricing_addons_id'), table_name='pricing_addons')
    op.drop_table('pricing_addons')

    op.drop_index(op.f('ix_pricing_services_kategori'), table_name='pricing_services')
    op.drop_index(op.f('ix_pricing_services_id'), table_name='pricing_services')
    op.drop_table('pricing_services')

    op.drop_index(op.f('ix_pricing_profiles_kod'), table_name='pricing_profiles')
    op.drop_index(op.f('ix_pricing_profiles_id'), table_name='pricing_profiles')
    op.drop_table('pricing_profiles')

    op.drop_index(op.f('ix_pricing_scales_kod'), table_name='pricing_scales')
    op.drop_index(op.f('ix_pricing_scales_id'), table_name='pricing_scales')
    op.drop_table('pricing_scales')
