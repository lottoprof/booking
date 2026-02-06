// frontend/ts/api.ts
/**
 * API client for web booking endpoints (/web/*)
 *
 * Uses Redis-only endpoints. No direct SQL access.
 */
// ──────────────────────────────────────────────────────────────────────────────
// API Client
// ──────────────────────────────────────────────────────────────────────────────
export class BookingAPI {
    constructor() {
        this.baseUrl = '/web';
    }
    /**
     * Get list of available services
     */
    async getServices() {
        const response = await fetch(`${this.baseUrl}/services`);
        if (!response.ok) {
            throw new Error(`Failed to fetch services: ${response.status}`);
        }
        return response.json();
    }
    /**
     * Get list of specialists, optionally filtered by service
     */
    async getSpecialists(serviceId) {
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
    async getLocations() {
        const response = await fetch(`${this.baseUrl}/locations`);
        if (!response.ok) {
            throw new Error(`Failed to fetch locations: ${response.status}`);
        }
        return response.json();
    }
    /**
     * Get calendar of available days
     */
    async getCalendar(locationId, serviceId, startDate, endDate) {
        const params = new URLSearchParams({
            location_id: String(locationId),
            service_id: String(serviceId),
        });
        if (startDate)
            params.append('start_date', startDate);
        if (endDate)
            params.append('end_date', endDate);
        const response = await fetch(`${this.baseUrl}/slots/calendar?${params}`);
        if (!response.ok) {
            throw new Error(`Failed to fetch calendar: ${response.status}`);
        }
        return response.json();
    }
    /**
     * Get available time slots for a specific day
     */
    async getDaySlots(locationId, serviceId, date, specialistId) {
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
    async reserveSlot(locationId, serviceId, date, time, specialistId) {
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
    async cancelReservation(uuid) {
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
    async createBooking(reserveUuid, phone, name) {
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
    async getBookingStatus(uuid) {
        const response = await fetch(`${this.baseUrl}/booking/${uuid}`);
        if (!response.ok) {
            throw new Error(`Failed to get booking status: ${response.status}`);
        }
        return response.json();
    }
    /**
     * Poll until booking is confirmed or failed
     */
    async waitForConfirmation(uuid, maxAttempts = 30, intervalMs = 1000) {
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
//# sourceMappingURL=api.js.map