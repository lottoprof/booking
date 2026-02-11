from sqlalchemy import Column, Enum, Float, ForeignKey, Integer, Table, Text, UniqueConstraint, text
from sqlalchemy.sql.sqltypes import NullType

from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()
metadata = Base.metadata


class Company(Base):
    __tablename__ = 'company'

    name = Column(Text, nullable=False)
    id = Column(Integer, primary_key=True)
    description = Column(Text)
    created_at = Column(Text, server_default=text('CURRENT_TIMESTAMP'))

    locations = relationship('Locations', back_populates='company')
    service_packages = relationship('ServicePackages', back_populates='company')
    services = relationship('Services', back_populates='company')
    users = relationship('Users', back_populates='company')
    bookings = relationship('Bookings', back_populates='company')


class Roles(Base):
    __tablename__ = 'roles'

    name = Column(Text, nullable=False, unique=True)
    id = Column(Integer, primary_key=True)

    user_roles = relationship('UserRoles', back_populates='role')


t_sqlite_sequence = Table(
    'sqlite_sequence', metadata,
    Column('name', NullType),
    Column('seq', NullType)
)


class Locations(Base):
    __tablename__ = 'locations'

    company_id = Column(ForeignKey('company.id', ondelete='CASCADE'), nullable=False)
    name = Column(Text, nullable=False)
    city = Column(Text, nullable=False)
    is_active = Column(Integer, nullable=False, server_default=text('1'))
    work_schedule = Column(Text, nullable=False, server_default=text("'{}'"))
    id = Column(Integer, primary_key=True)
    country = Column(Text)
    region = Column(Text)
    street = Column(Text)
    house = Column(Text)
    building = Column(Text)
    office = Column(Text)
    postal_code = Column(Text)
    notes = Column(Text)
    remind_before_minutes = Column(Integer, nullable=False, server_default=text('120'))

    company = relationship('Company', back_populates='locations')
    rooms = relationship('Rooms', back_populates='location')
    user_roles = relationship('UserRoles', back_populates='location')
    bookings = relationship('Bookings', back_populates='location')


class ServicePackages(Base):
    __tablename__ = 'service_packages'

    company_id = Column(ForeignKey('company.id', ondelete='CASCADE'), nullable=False)
    name = Column(Text, nullable=False)
    package_items = Column(Text, nullable=False, server_default=text("'[]'"))
    is_active = Column(Integer, nullable=False, server_default=text('1'))
    id = Column(Integer, primary_key=True)
    description = Column(Text)
    show_on_pricing = Column(Integer, nullable=False, server_default=text('1'))
    show_on_booking = Column(Integer, nullable=False, server_default=text('1'))

    company = relationship('Company', back_populates='service_packages')
    client_packages = relationship('ClientPackages', back_populates='package')
    bookings = relationship('Bookings', back_populates='service_package')


class Services(Base):
    __tablename__ = 'services'

    company_id = Column(ForeignKey('company.id', ondelete='CASCADE'), nullable=False)
    name = Column(Text, nullable=False)
    duration_min = Column(Integer, nullable=False)
    break_min = Column(Integer, nullable=False, server_default=text('0'))
    price = Column(Float, nullable=False)
    price_5 = Column(Float)
    price_10 = Column(Float)
    is_active = Column(Integer, nullable=False, server_default=text('1'))
    id = Column(Integer, primary_key=True)
    description = Column(Text)
    category = Column(Text)
    color_code = Column(Text)

    company = relationship('Company', back_populates='services')
    bookings = relationship('Bookings', back_populates='service')
    service_rooms = relationship('ServiceRooms', back_populates='service')


class Users(Base):
    __tablename__ = 'users'

    company_id = Column(ForeignKey('company.id', ondelete='CASCADE'), nullable=False)
    first_name = Column(Text, nullable=False)
    is_active = Column(Integer, nullable=False, server_default=text('1'))
    id = Column(Integer, primary_key=True)
    last_name = Column(Text)
    middle_name = Column(Text)
    email = Column(Text)
    phone = Column(Text)
    tg_id = Column(Integer)
    tg_username = Column(Text)
    birth_date = Column(Text)
    gender = Column(Enum('male', 'female', 'other'))
    notes = Column(Text)
    created_at = Column(Text, server_default=text('CURRENT_TIMESTAMP'))
    updated_at = Column(Text, server_default=text('CURRENT_TIMESTAMP'))

    company = relationship('Company', back_populates='users')
    calendar_overrides = relationship('CalendarOverrides', back_populates='users')
    client_discounts = relationship('ClientDiscounts', back_populates='user')
    client_packages = relationship('ClientPackages', back_populates='user')
    client_wallets = relationship('ClientWallets', back_populates='user')
    push_subscriptions = relationship('PushSubscriptions', back_populates='user')
    specialists = relationship('Specialists', uselist=False, back_populates='user')
    user_roles = relationship('UserRoles', back_populates='user')
    bookings = relationship('Bookings', back_populates='client')
    wallet_transactions = relationship('WalletTransactions', back_populates='users')
    integrations = relationship('SpecialistIntegrations', back_populates='user')


class CalendarOverrides(Base):
    __tablename__ = 'calendar_overrides'

    target_type = Column(Text, nullable=False)
    date_start = Column(Text, nullable=False)
    date_end = Column(Text, nullable=False)
    override_kind = Column(Text, nullable=False)
    id = Column(Integer, primary_key=True)
    target_id = Column(Integer)
    reason = Column(Text)
    created_by = Column(ForeignKey('users.id', ondelete='SET NULL'))
    created_at = Column(Text, server_default=text('CURRENT_TIMESTAMP'))

    users = relationship('Users', back_populates='calendar_overrides')


class ClientDiscounts(Base):
    __tablename__ = 'client_discounts'

    user_id = Column(ForeignKey('users.id', ondelete='CASCADE'))  # NULL = promo for all
    discount_percent = Column(Float, nullable=False, server_default=text('0'))
    id = Column(Integer, primary_key=True)
    valid_from = Column(Text)
    valid_to = Column(Text)
    description = Column(Text)

    user = relationship('Users', back_populates='client_discounts')


class ClientPackages(Base):
    __tablename__ = 'client_packages'

    user_id = Column(ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    package_id = Column(ForeignKey('service_packages.id', ondelete='CASCADE'), nullable=False)
    used_quantity = Column(Integer, nullable=False, server_default=text('0'))
    purchased_at = Column(Text, nullable=False, server_default=text('CURRENT_TIMESTAMP'))
    id = Column(Integer, primary_key=True)
    valid_to = Column(Text)
    notes = Column(Text)
    used_items = Column(Text, nullable=False, server_default=text("'{}'"))
    is_closed = Column(Integer, nullable=False, server_default=text('0'))
    purchase_price = Column(Float)

    package = relationship('ServicePackages', back_populates='client_packages')
    user = relationship('Users', back_populates='client_packages')
    bookings = relationship('Bookings', back_populates='client_package')


class ClientWallets(Base):
    __tablename__ = 'client_wallets'

    user_id = Column(ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    balance = Column(Float, nullable=False, server_default=text('0'))
    currency = Column(Text, nullable=False, server_default=text("'RUB'"))
    is_blocked = Column(Integer, nullable=False, server_default=text('0'))
    id = Column(Integer, primary_key=True)

    user = relationship('Users', back_populates='client_wallets')
    wallet_transactions = relationship('WalletTransactions', back_populates='wallet')


class PushSubscriptions(Base):
    __tablename__ = 'push_subscriptions'

    user_id = Column(ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    endpoint = Column(Text, nullable=False)
    created_at = Column(Text, nullable=False, server_default=text('CURRENT_TIMESTAMP'))
    id = Column(Integer, primary_key=True)
    auth = Column(Text)
    p256dh = Column(Text)

    user = relationship('Users', back_populates='push_subscriptions')

class Rooms(Base):
    __tablename__ = 'rooms'
    __table_args__ = (
        UniqueConstraint('location_id', 'name'),
    )

    id = Column(Integer, primary_key=True)
    location_id = Column(ForeignKey('locations.id', ondelete='CASCADE'), nullable=False)
    name = Column(Text, nullable=False)
    display_order = Column(Integer)
    notes = Column(Text)
    is_active = Column(Integer, nullable=False, server_default=text('1'))

    location = relationship('Locations', back_populates='rooms')
    bookings = relationship('Bookings', back_populates='room')
    service_rooms = relationship('ServiceRooms', back_populates='room')

class Specialists(Base):
    __tablename__ = 'specialists'

    user_id = Column(ForeignKey('users.id', ondelete='CASCADE'), nullable=False, unique=True)
    work_schedule = Column(Text, nullable=False, server_default=text("'{}'"))
    id = Column(Integer, primary_key=True)
    display_name = Column(Text)
    description = Column(Text)
    photo_url = Column(Text)
    is_active = Column(Integer, server_default=text('1'))
    created_at = Column(Text, server_default=text('CURRENT_TIMESTAMP'))
    updated_at = Column(Text, server_default=text('CURRENT_TIMESTAMP'))

    user = relationship('Users', back_populates='specialists')
    bookings = relationship('Bookings', back_populates='specialist')
    integrations = relationship('SpecialistIntegrations', back_populates='specialist')


class UserRoles(Base):
    __tablename__ = 'user_roles'
    __table_args__ = (
        UniqueConstraint('user_id', 'role_id', 'location_id'),
    )

    user_id = Column(ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    role_id = Column(ForeignKey('roles.id', ondelete='CASCADE'), nullable=False)
    id = Column(Integer, primary_key=True)
    location_id = Column(ForeignKey('locations.id', ondelete='CASCADE'))

    location = relationship('Locations', back_populates='user_roles')
    role = relationship('Roles', back_populates='user_roles')
    user = relationship('Users', back_populates='user_roles')


class Bookings(Base):
    __tablename__ = 'bookings'

    company_id = Column(ForeignKey('company.id', ondelete='CASCADE'), nullable=False)
    location_id = Column(ForeignKey('locations.id'), nullable=False)
    service_id = Column(ForeignKey('services.id'))  # nullable for preset-based bookings
    service_package_id = Column(ForeignKey('service_packages.id'))  # preset
    client_id = Column(ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    specialist_id = Column(ForeignKey('specialists.id', ondelete='CASCADE'), nullable=False)
    date_start = Column(Text, nullable=False)
    date_end = Column(Text, nullable=False)
    duration_minutes = Column(Integer, nullable=False)
    break_minutes = Column(Integer, nullable=False, server_default=text('0'))
    status = Column(Text, nullable=False, server_default=text("'pending'"))
    created_at = Column(Text, nullable=False, server_default=text('CURRENT_TIMESTAMP'))
    updated_at = Column(Text, nullable=False, server_default=text('CURRENT_TIMESTAMP'))
    id = Column(Integer, primary_key=True)
    room_id = Column(ForeignKey('rooms.id'))
    final_price = Column(Float)
    notes = Column(Text)
    cancel_reason = Column(Text)
    client_package_id = Column(ForeignKey('client_packages.id', ondelete='SET NULL'))

    client = relationship('Users', back_populates='bookings')
    company = relationship('Company', back_populates='bookings')
    location = relationship('Locations', back_populates='bookings')
    room = relationship('Rooms', back_populates='bookings')
    service = relationship('Services', back_populates='bookings')
    service_package = relationship('ServicePackages', back_populates='bookings')
    specialist = relationship('Specialists', back_populates='bookings')
    booking_discounts = relationship('BookingDiscounts', back_populates='booking')
    wallet_transactions = relationship('WalletTransactions', back_populates='booking')
    client_package = relationship('ClientPackages', back_populates='bookings')
    external_events = relationship('BookingExternalEvents', back_populates='booking')


class ServiceRooms(Base):
    __tablename__ = 'service_rooms'
    __table_args__ = (
        UniqueConstraint('room_id', 'service_id'),
    )

    room_id = Column(ForeignKey('rooms.id', ondelete='CASCADE'), nullable=False)
    service_id = Column(ForeignKey('services.id', ondelete='CASCADE'), nullable=False)
    is_active = Column(Integer, nullable=False, server_default=text('1'))
    id = Column(Integer, primary_key=True)
    notes = Column(Text)

    room = relationship('Rooms', back_populates='service_rooms')
    service = relationship('Services', back_populates='service_rooms')


t_specialist_services = Table(
    'specialist_services', metadata,
    Column('service_id', ForeignKey('services.id', ondelete='CASCADE'), nullable=False),
    Column('specialist_id', ForeignKey('specialists.id', ondelete='CASCADE'), nullable=False),
    Column('is_default', Integer, nullable=False, server_default=text('0')),
    Column('is_active', Integer, nullable=False, server_default=text('1')),
    Column('notes', Text),
    UniqueConstraint('service_id', 'specialist_id')
)


class BookingDiscounts(Base):
    __tablename__ = 'booking_discounts'

    booking_id = Column(ForeignKey('bookings.id', ondelete='CASCADE'), nullable=False)
    discount_percent = Column(Float, nullable=False, server_default=text('0'))
    id = Column(Integer, primary_key=True)
    discount_reason = Column(Text)

    booking = relationship('Bookings', back_populates='booking_discounts')


class WalletTransactions(Base):
    __tablename__ = 'wallet_transactions'

    wallet_id = Column(ForeignKey('client_wallets.id', ondelete='CASCADE'), nullable=False)
    amount = Column(Float, nullable=False)
    type = Column(Enum('deposit', 'withdraw', 'payment', 'refund', 'correction'), nullable=False, server_default=text("'payment'"))
    created_at = Column(Text, nullable=False, server_default=text('CURRENT_TIMESTAMP'))
    id = Column(Integer, primary_key=True)
    booking_id = Column(ForeignKey('bookings.id', ondelete='SET NULL'))
    description = Column(Text)
    created_by = Column(ForeignKey('users.id', ondelete='SET NULL'))

    booking = relationship('Bookings', back_populates='wallet_transactions')
    users = relationship('Users', back_populates='wallet_transactions')
    wallet = relationship('ClientWallets', back_populates='wallet_transactions')

class NotificationSettings(Base):
    __tablename__ = 'notification_settings'
    __table_args__ = (
        UniqueConstraint('event_type', 'recipient_role', 'channel', 'company_id'),
    )

    id = Column(Integer, primary_key=True)
    event_type = Column(Text, nullable=False)
    recipient_role = Column(Text, nullable=False)
    channel = Column(Text, nullable=False, server_default=text("'all'"))
    enabled = Column(Integer, nullable=False, server_default=text('1'))
    ad_template_id = Column(Integer)
    company_id = Column(ForeignKey('company.id', ondelete='CASCADE'), nullable=False)


class AdTemplates(Base):
    __tablename__ = 'ad_templates'

    id = Column(Integer, primary_key=True)
    name = Column(Text, nullable=False)
    content_tg = Column(Text, nullable=False)
    content_html = Column(Text)
    active = Column(Integer, nullable=False, server_default=text('1'))
    valid_until = Column(Text)
    company_id = Column(ForeignKey('company.id', ondelete='CASCADE'), nullable=False)


class AuditLog(Base):
    __tablename__ = 'audit_log'

    id = Column(Integer, primary_key=True)
    event_type = Column(Text, nullable=False)

    actor_user_id = Column(
        ForeignKey('users.id', ondelete='SET NULL')
    )
    target_user_id = Column(
        ForeignKey('users.id', ondelete='SET NULL')
    )

    payload = Column(Text)
    created_at = Column(
        Text,
        nullable=False,
        server_default=text('CURRENT_TIMESTAMP')
    )

    actor_user = relationship(
        'Users',
        foreign_keys=[actor_user_id]
    )
    target_user = relationship(
        'Users',
        foreign_keys=[target_user_id]
    )


class SpecialistIntegrations(Base):
    __tablename__ = 'specialist_integrations'
    __table_args__ = (
        UniqueConstraint('specialist_id', 'provider'),
    )

    id = Column(Integer, primary_key=True)
    specialist_id = Column(ForeignKey('specialists.id', ondelete='CASCADE'))
    user_id = Column(ForeignKey('users.id', ondelete='CASCADE'))
    provider = Column(Text, nullable=False, server_default=text("'google_calendar'"))
    access_token = Column(Text)
    refresh_token = Column(Text)
    token_expires_at = Column(Text)
    calendar_id = Column(Text, server_default=text("'primary'"))
    sync_enabled = Column(Integer, server_default=text('1'))
    sync_scope = Column(Text, server_default=text("'own'"))
    location_id = Column(ForeignKey('locations.id', ondelete='CASCADE'))
    last_sync_at = Column(Text)
    created_at = Column(Text, server_default=text('CURRENT_TIMESTAMP'))
    updated_at = Column(Text, server_default=text('CURRENT_TIMESTAMP'))

    specialist = relationship('Specialists', back_populates='integrations')
    user = relationship('Users', back_populates='integrations')
    location = relationship('Locations')
    booking_external_events = relationship('BookingExternalEvents', back_populates='specialist_integration')


class BookingExternalEvents(Base):
    __tablename__ = 'booking_external_events'
    __table_args__ = (
        UniqueConstraint('booking_id', 'specialist_integration_id'),
    )

    id = Column(Integer, primary_key=True)
    booking_id = Column(ForeignKey('bookings.id', ondelete='CASCADE'), nullable=False)
    provider = Column(Text, nullable=False, server_default=text("'google_calendar'"))
    external_event_id = Column(Text, nullable=False)
    specialist_integration_id = Column(ForeignKey('specialist_integrations.id', ondelete='CASCADE'), nullable=False)
    created_at = Column(Text, server_default=text('CURRENT_TIMESTAMP'))

    booking = relationship('Bookings', back_populates='external_events')
    specialist_integration = relationship('SpecialistIntegrations', back_populates='booking_external_events')

