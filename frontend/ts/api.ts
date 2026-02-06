// frontend/ts/api.ts
/**
 * API client for web booking endpoints (/web/*)
 *
 * Uses Redis-only endpoints. No direct SQL access.
 */

// ──────────────────────────────────────────────────────────────────────────────
// Types
// ──────────────────────────────────────────────────────────────────────────────

export interface Service {
  id: number;
  name: string;
  description: string | null;
  category: string | null;
  duration_min: number;
  price: number;
}

export interface Specialist {
  id: number;
  name: string;
  description: string | null;
  photo_url: string | null;
}

export interface Location {
  id: number;
  name: string;
  address: string | null;
}

export interface DayStatus {
  date: string;
  has_slots: boolean;
  open_slots_count: number;
}

export interface CalendarResponse {
  location_id: number;
  days: DayStatus[];
}

export interface TimeSlot {
  time: string;
  available: boolean;
  specialists: Specialist[];
}

export interface DaySlotsResponse {
  location_id: number;
  service_id: number;
  date: string;
  slots: TimeSlot[];
}

export interface SlotReserveResponse {
  uuid: string;
  expires_in: number;
}

export interface PendingBooking {
  uuid: string;
  status: 'pending' | 'processing' | 'confirmed' | 'failed';
  booking_id?: number;
  error?: string;
}

// ──────────────────────────────────────────────────────────────────────────────
// API Client
// ──────────────────────────────────────────────────────────────────────────────

export class BookingAPI {
  private baseUrl = '/web';

  /**
   * Get list of available services
   */
  async getServices(): Promise<Service[]> {
    const response = await fetch(`${this.baseUrl}/services`);
    if (!response.ok) {
      throw new Error(`Failed to fetch services: ${response.status}`);
    }
    return response.json();
  }

  /**
   * Get list of specialists, optionally filtered by service
   */
  async getSpecialists(serviceId?: number): Promise<Specialist[]> {
    let url = `${this.baseUrl}/specialists`;
    if (serviceId !== undefined) {
      url += `?service_id=${serviceId}`;
    }
    const response = await fetch(url);
    if (!response.ok) {
      throw new Error(`Failed to fetch specialists: ${response.status}`);
    }
    return response.json();
  }

  /**
   * Get list of locations
   */
  async getLocations(): Promise<Location[]> {
    const response = await fetch(`${this.baseUrl}/locations`);
    if (!response.ok) {
      throw new Error(`Failed to fetch locations: ${response.status}`);
    }
    return response.json();
  }

  /**
   * Get calendar of available days
   */
  async getCalendar(
    locationId: number,
    serviceId: number,
    startDate?: string,
    endDate?: string
  ): Promise<CalendarResponse> {
    const params = new URLSearchParams({
      location_id: String(locationId),
      service_id: String(serviceId),
    });
    if (startDate) params.append('start_date', startDate);
    if (endDate) params.append('end_date', endDate);

    const response = await fetch(`${this.baseUrl}/slots/calendar?${params}`);
    if (!response.ok) {
      throw new Error(`Failed to fetch calendar: ${response.status}`);
    }
    return response.json();
  }

  /**
   * Get available time slots for a specific day
   */
  async getDaySlots(
    locationId: number,
    serviceId: number,
    date: string,
    specialistId?: number
  ): Promise<DaySlotsResponse> {
    const params = new URLSearchParams({
      location_id: String(locationId),
      service_id: String(serviceId),
      date: date,
    });
    if (specialistId !== undefined) {
      params.append('specialist_id', String(specialistId));
    }

    const response = await fetch(`${this.baseUrl}/slots/day?${params}`);
    if (!response.ok) {
      throw new Error(`Failed to fetch day slots: ${response.status}`);
    }
    return response.json();
  }

  /**
   * Reserve a time slot (5 minute hold)
   */
  async reserveSlot(
    locationId: number,
    serviceId: number,
    date: string,
    time: string,
    specialistId?: number
  ): Promise<SlotReserveResponse> {
    const response = await fetch(`${this.baseUrl}/reserve`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        location_id: locationId,
        service_id: serviceId,
        specialist_id: specialistId ?? null,
        date: date,
        time: time,
      }),
    });

    if (response.status === 409) {
      throw new Error('Slot already reserved by another user');
    }
    if (!response.ok) {
      throw new Error(`Failed to reserve slot: ${response.status}`);
    }
    return response.json();
  }

  /**
   * Cancel a slot reservation
   */
  async cancelReservation(uuid: string): Promise<void> {
    const response = await fetch(`${this.baseUrl}/reserve/${uuid}`, {
      method: 'DELETE',
    });
    if (!response.ok && response.status !== 404) {
      throw new Error(`Failed to cancel reservation: ${response.status}`);
    }
  }

  /**
   * Create a pending booking from a reservation
   */
  async createBooking(
    reserveUuid: string,
    phone: string,
    name?: string
  ): Promise<PendingBooking> {
    const response = await fetch(`${this.baseUrl}/booking`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        reserve_uuid: reserveUuid,
        phone: phone,
        name: name ?? null,
      }),
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(error.detail || `Failed to create booking: ${response.status}`);
    }
    return response.json();
  }

  /**
   * Get status of a pending booking
   */
  async getBookingStatus(uuid: string): Promise<PendingBooking> {
    const response = await fetch(`${this.baseUrl}/booking/${uuid}`);
    if (!response.ok) {
      throw new Error(`Failed to get booking status: ${response.status}`);
    }
    return response.json();
  }

  /**
   * Poll until booking is confirmed or failed
   */
  async waitForConfirmation(
    uuid: string,
    maxAttempts = 30,
    intervalMs = 1000
  ): Promise<PendingBooking> {
    for (let i = 0; i < maxAttempts; i++) {
      const status = await this.getBookingStatus(uuid);
      if (status.status === 'confirmed' || status.status === 'failed') {
        return status;
      }
      await new Promise((resolve) => setTimeout(resolve, intervalMs));
    }
    throw new Error('Timeout waiting for booking confirmation');
  }
}

// Export singleton instance
export const api = new BookingAPI();
