// frontend/ts/booking.ts
/**
 * Booking Wizard Application
 *
 * Step-based booking flow:
 * 1. Service selection
 * 2. Specialist selection (optional)
 * 3. Calendar (date selection)
 * 4. Time selection
 * 5. Contact info (phone, name)
 * 6. Confirmation/Result
 */

import { api, Service, Specialist, TimeSlot, PendingBooking } from './api.js';

type Step = 'service' | 'specialist' | 'calendar' | 'time' | 'phone' | 'confirm';

interface BookingState {
  locationId: number;
  service: Service | null;
  specialist: Specialist | null;
  date: string;
  time: string;
  phone: string;
  name: string;
  reserveUuid: string;
  bookingUuid: string;
}

class BookingApp {
  private currentStep: Step = 'service';
  private state: BookingState = {
    locationId: 1, // Default location, will be loaded
    service: null,
    specialist: null,
    date: '',
    time: '',
    phone: '',
    name: '',
    reserveUuid: '',
    bookingUuid: '',
  };

  private services: Service[] = [];
  private specialists: Specialist[] = [];
  private availableDays: Map<string, boolean> = new Map();
  private timeSlots: TimeSlot[] = [];

  private reserveTimer: number | null = null;
  private reserveExpireTime: number = 0;

  private currentMonth: Date = new Date();

  constructor() {
    this.initEventListeners();
    this.loadInitialData();
  }

  // ──────────────────────────────────────────────────────────────────────────────
  // Initialization
  // ──────────────────────────────────────────────────────────────────────────────

  private async loadInitialData(): Promise<void> {
    try {
      // Load locations and use first one
      const locations = await api.getLocations();
      if (locations.length > 0) {
        this.state.locationId = locations[0].id;
      }

      // Load services
      this.services = await api.getServices();
      this.renderServices();
      this.showStep('service');
    } catch (error) {
      console.error('Failed to load initial data:', error);
      this.showError('Не удалось загрузить данные. Попробуйте обновить страницу.');
    }
  }

  private initEventListeners(): void {
    // Back links
    document.querySelectorAll('[data-back]').forEach((el) => {
      el.addEventListener('click', (e) => {
        e.preventDefault();
        const target = (el as HTMLElement).dataset.back as Step;
        this.goBack(target);
      });
    });

    // Any specialist button
    document.getElementById('any-specialist-btn')?.addEventListener('click', () => {
      this.state.specialist = null;
      this.loadCalendar();
    });

    // Calendar navigation
    document.getElementById('prev-month')?.addEventListener('click', () => {
      this.currentMonth.setMonth(this.currentMonth.getMonth() - 1);
      this.renderCalendar();
    });

    document.getElementById('next-month')?.addEventListener('click', () => {
      this.currentMonth.setMonth(this.currentMonth.getMonth() + 1);
      this.renderCalendar();
    });

    // Contact form
    document.getElementById('contact-form')?.addEventListener('submit', (e) => {
      e.preventDefault();
      this.submitBooking();
    });

    // Try again button
    document.getElementById('try-again-btn')?.addEventListener('click', () => {
      this.reset();
    });

    // Service click delegation
    document.getElementById('services-list')?.addEventListener('click', (e) => {
      const card = (e.target as HTMLElement).closest('.service-card');
      if (card) {
        const id = parseInt(card.getAttribute('data-id') || '0');
        this.selectService(id);
      }
    });

    // Specialist click delegation
    document.getElementById('specialists-list')?.addEventListener('click', (e) => {
      const card = (e.target as HTMLElement).closest('.specialist-card');
      if (card) {
        const id = parseInt(card.getAttribute('data-id') || '0');
        this.selectSpecialist(id);
      }
    });

    // Calendar day click delegation
    document.getElementById('calendar-days')?.addEventListener('click', (e) => {
      const day = (e.target as HTMLElement).closest('.calendar-day');
      if (day && day.classList.contains('available')) {
        const date = day.getAttribute('data-date');
        if (date) {
          this.selectDate(date);
        }
      }
    });

    // Time slot click delegation
    document.getElementById('time-slots')?.addEventListener('click', (e) => {
      const slot = (e.target as HTMLElement).closest('.time-slot');
      if (slot && !slot.classList.contains('unavailable')) {
        const time = slot.getAttribute('data-time');
        if (time) {
          this.selectTime(time);
        }
      }
    });
  }

  // ──────────────────────────────────────────────────────────────────────────────
  // Step Navigation
  // ──────────────────────────────────────────────────────────────────────────────

  private showStep(step: Step): void {
    // Hide all steps
    document.querySelectorAll('.step').forEach((el) => {
      el.classList.remove('active');
    });

    // Show current step
    const stepEl = document.getElementById(`step-${step}`);
    if (stepEl) {
      stepEl.classList.add('active');
    }

    // Update progress bar
    const stepOrder: Step[] = ['service', 'specialist', 'calendar', 'time', 'phone', 'confirm'];
    const stepIndex = stepOrder.indexOf(step);

    document.querySelectorAll('.progress-step').forEach((el, i) => {
      el.classList.remove('completed', 'active');
      if (i < stepIndex) {
        el.classList.add('completed');
      } else if (i === stepIndex) {
        el.classList.add('active');
      }
    });

    this.currentStep = step;
  }

  private goBack(target: Step): void {
    // Cancel reservation if going back from phone step
    if (this.currentStep === 'phone' && this.state.reserveUuid) {
      this.cancelReservation();
    }

    this.showStep(target);
  }

  // ──────────────────────────────────────────────────────────────────────────────
  // Service Selection
  // ──────────────────────────────────────────────────────────────────────────────

  private renderServices(): void {
    const container = document.getElementById('services-list');
    if (!container) return;

    if (this.services.length === 0) {
      container.innerHTML = `
        <div class="text-center py-8 text-gray-400">
          Услуги не найдены
        </div>
      `;
      return;
    }

    container.innerHTML = this.services
      .map(
        (s) => `
      <div class="service-card" data-id="${s.id}">
        <div class="flex justify-between items-start">
          <div>
            <div class="name">${this.escapeHtml(s.name)}</div>
            <div class="details">${s.duration_min} мин</div>
          </div>
          <div class="price">${this.formatPrice(s.price)}</div>
        </div>
      </div>
    `
      )
      .join('');
  }

  private selectService(id: number): void {
    const service = this.services.find((s) => s.id === id);
    if (!service) return;

    this.state.service = service;

    // Highlight selected
    document.querySelectorAll('.service-card').forEach((el) => {
      el.classList.remove('selected');
      if (el.getAttribute('data-id') === String(id)) {
        el.classList.add('selected');
      }
    });

    // Load specialists and show next step
    this.loadSpecialists();
  }

  // ──────────────────────────────────────────────────────────────────────────────
  // Specialist Selection
  // ──────────────────────────────────────────────────────────────────────────────

  private async loadSpecialists(): Promise<void> {
    try {
      this.specialists = await api.getSpecialists(this.state.service?.id);
      this.renderSpecialists();
      this.showStep('specialist');
    } catch (error) {
      console.error('Failed to load specialists:', error);
      // Skip to calendar if specialists can't be loaded
      this.loadCalendar();
    }
  }

  private renderSpecialists(): void {
    const container = document.getElementById('specialists-list');
    if (!container) return;

    if (this.specialists.length === 0) {
      container.innerHTML = `
        <div class="text-center py-4 text-gray-400">
          Специалисты не указаны
        </div>
      `;
      return;
    }

    container.innerHTML = this.specialists
      .map(
        (s) => `
      <div class="specialist-card" data-id="${s.id}">
        <div class="avatar">
          ${
            s.photo_url
              ? `<img src="${this.escapeHtml(s.photo_url)}" alt="${this.escapeHtml(s.name)}">`
              : s.name.charAt(0).toUpperCase()
          }
        </div>
        <div>
          <div class="font-semibold text-gray-800">${this.escapeHtml(s.name)}</div>
          ${s.description ? `<div class="text-sm text-gray-500">${this.escapeHtml(s.description)}</div>` : ''}
        </div>
      </div>
    `
      )
      .join('');
  }

  private selectSpecialist(id: number): void {
    const specialist = this.specialists.find((s) => s.id === id);
    if (!specialist) return;

    this.state.specialist = specialist;

    // Highlight selected
    document.querySelectorAll('.specialist-card').forEach((el) => {
      el.classList.remove('selected');
      if (el.getAttribute('data-id') === String(id)) {
        el.classList.add('selected');
      }
    });

    this.loadCalendar();
  }

  // ──────────────────────────────────────────────────────────────────────────────
  // Calendar Selection
  // ──────────────────────────────────────────────────────────────────────────────

  private async loadCalendar(): Promise<void> {
    if (!this.state.service) return;

    try {
      const calendar = await api.getCalendar(
        this.state.locationId,
        this.state.service.id
      );

      this.availableDays.clear();
      for (const day of calendar.days) {
        this.availableDays.set(day.date, day.has_slots);
      }

      // Set current month to first available date
      const firstAvailable = calendar.days.find((d) => d.has_slots);
      if (firstAvailable) {
        this.currentMonth = new Date(firstAvailable.date);
      } else {
        this.currentMonth = new Date();
      }

      this.renderCalendar();
      this.showStep('calendar');
    } catch (error) {
      console.error('Failed to load calendar:', error);
      this.showError('Не удалось загрузить календарь');
    }
  }

  private renderCalendar(): void {
    const container = document.getElementById('calendar-days');
    const monthDisplay = document.getElementById('current-month');
    if (!container || !monthDisplay) return;

    const year = this.currentMonth.getFullYear();
    const month = this.currentMonth.getMonth();

    // Update month display
    const monthNames = [
      'Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
      'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь'
    ];
    monthDisplay.textContent = `${monthNames[month]} ${year}`;

    // Calculate days
    const firstDay = new Date(year, month, 1);
    const lastDay = new Date(year, month + 1, 0);
    const startOffset = (firstDay.getDay() + 6) % 7; // Monday = 0

    const today = new Date();
    today.setHours(0, 0, 0, 0);

    let html = '';

    // Empty cells before first day
    for (let i = 0; i < startOffset; i++) {
      html += '<div class="calendar-day empty"></div>';
    }

    // Days of month
    for (let day = 1; day <= lastDay.getDate(); day++) {
      const date = new Date(year, month, day);
      const dateStr = date.toISOString().split('T')[0];
      const isPast = date < today;
      const isToday = date.getTime() === today.getTime();
      const isAvailable = !isPast && this.availableDays.get(dateStr);
      const isSelected = dateStr === this.state.date;

      let classes = ['calendar-day'];
      if (isToday) classes.push('today');
      if (isAvailable) classes.push('available');
      if (!isAvailable || isPast) classes.push('unavailable');
      if (isSelected) classes.push('selected');

      html += `<div class="${classes.join(' ')}" data-date="${dateStr}">${day}</div>`;
    }

    container.innerHTML = html;

    // Update navigation buttons
    const prevBtn = document.getElementById('prev-month') as HTMLButtonElement;
    const nextBtn = document.getElementById('next-month') as HTMLButtonElement;

    if (prevBtn) {
      prevBtn.disabled = month <= today.getMonth() && year <= today.getFullYear();
    }
    if (nextBtn) {
      const maxMonth = new Date();
      maxMonth.setDate(maxMonth.getDate() + 30);
      nextBtn.disabled = month >= maxMonth.getMonth() && year >= maxMonth.getFullYear();
    }
  }

  private selectDate(date: string): void {
    this.state.date = date;

    // Update selected state
    document.querySelectorAll('.calendar-day').forEach((el) => {
      el.classList.remove('selected');
      if (el.getAttribute('data-date') === date) {
        el.classList.add('selected');
      }
    });

    this.loadTimeSlots();
  }

  // ──────────────────────────────────────────────────────────────────────────────
  // Time Selection
  // ──────────────────────────────────────────────────────────────────────────────

  private async loadTimeSlots(): Promise<void> {
    if (!this.state.service) return;

    try {
      const slotsResponse = await api.getDaySlots(
        this.state.locationId,
        this.state.service.id,
        this.state.date,
        this.state.specialist?.id
      );

      this.timeSlots = slotsResponse.slots;
      this.renderTimeSlots();

      // Update date display
      const dateDisplay = document.getElementById('selected-date-display');
      if (dateDisplay) {
        const date = new Date(this.state.date);
        const options: Intl.DateTimeFormatOptions = {
          weekday: 'long',
          day: 'numeric',
          month: 'long'
        };
        dateDisplay.textContent = date.toLocaleDateString('ru-RU', options);
      }

      this.showStep('time');
    } catch (error) {
      console.error('Failed to load time slots:', error);
      this.showError('Не удалось загрузить расписание');
    }
  }

  private renderTimeSlots(): void {
    const container = document.getElementById('time-slots');
    const noSlotsMsg = document.getElementById('no-slots-message');
    if (!container || !noSlotsMsg) return;

    if (this.timeSlots.length === 0) {
      container.innerHTML = '';
      noSlotsMsg.classList.remove('hidden');
      return;
    }

    noSlotsMsg.classList.add('hidden');

    container.innerHTML = this.timeSlots
      .map((slot) => {
        const classes = ['time-slot'];
        if (!slot.available) classes.push('unavailable');
        if (slot.time === this.state.time) classes.push('selected');

        return `<div class="${classes.join(' ')}" data-time="${slot.time}">${slot.time}</div>`;
      })
      .join('');
  }

  private async selectTime(time: string): Promise<void> {
    // Find specialists for this time
    const slot = this.timeSlots.find((s) => s.time === time);
    if (!slot) return;

    this.state.time = time;

    // If no specialist selected, pick first available from this slot
    if (!this.state.specialist && slot.specialists.length > 0) {
      this.state.specialist = slot.specialists[0];
    }

    // Update selected state
    document.querySelectorAll('.time-slot').forEach((el) => {
      el.classList.remove('selected');
      if (el.getAttribute('data-time') === time) {
        el.classList.add('selected');
      }
    });

    // Reserve the slot
    await this.reserveSlot();
  }

  // ──────────────────────────────────────────────────────────────────────────────
  // Reservation
  // ──────────────────────────────────────────────────────────────────────────────

  private async reserveSlot(): Promise<void> {
    if (!this.state.service) return;

    try {
      const result = await api.reserveSlot(
        this.state.locationId,
        this.state.service.id,
        this.state.date,
        this.state.time,
        this.state.specialist?.id
      );

      this.state.reserveUuid = result.uuid;
      this.startReserveTimer(result.expires_in);
      this.showStep('phone');
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : 'Ошибка резервирования';
      if (message.includes('already reserved')) {
        this.showError('Этот слот уже занят. Выберите другое время.');
        this.loadTimeSlots(); // Refresh slots
      } else {
        console.error('Failed to reserve slot:', error);
        this.showError('Не удалось зарезервировать время');
      }
    }
  }

  private cancelReservation(): void {
    if (this.state.reserveUuid) {
      api.cancelReservation(this.state.reserveUuid).catch((err) => {
        console.error('Failed to cancel reservation:', err);
      });
      this.state.reserveUuid = '';
    }
    this.stopReserveTimer();
  }

  private startReserveTimer(seconds: number): void {
    this.stopReserveTimer();

    this.reserveExpireTime = Date.now() + seconds * 1000;
    this.updateTimerDisplay();

    this.reserveTimer = window.setInterval(() => {
      this.updateTimerDisplay();
    }, 1000);
  }

  private stopReserveTimer(): void {
    if (this.reserveTimer) {
      clearInterval(this.reserveTimer);
      this.reserveTimer = null;
    }
  }

  private updateTimerDisplay(): void {
    const timerEl = document.getElementById('timer-display');
    const timerContainer = document.getElementById('reserve-timer');
    if (!timerEl || !timerContainer) return;

    const remaining = Math.max(0, Math.floor((this.reserveExpireTime - Date.now()) / 1000));
    const minutes = Math.floor(remaining / 60);
    const seconds = remaining % 60;

    timerEl.textContent = `${minutes}:${seconds.toString().padStart(2, '0')}`;

    // Warning state when < 1 minute
    if (remaining < 60) {
      timerContainer.classList.add('warning');
    } else {
      timerContainer.classList.remove('warning');
    }

    // Expired
    if (remaining === 0) {
      this.stopReserveTimer();
      this.state.reserveUuid = '';
      this.showError('Время резервирования истекло. Выберите время заново.');
      this.showStep('time');
    }
  }

  // ──────────────────────────────────────────────────────────────────────────────
  // Booking Submission
  // ──────────────────────────────────────────────────────────────────────────────

  private async submitBooking(): Promise<void> {
    const phoneInput = document.getElementById('phone-input') as HTMLInputElement;
    const nameInput = document.getElementById('name-input') as HTMLInputElement;
    const submitBtn = document.getElementById('submit-btn') as HTMLButtonElement;

    if (!phoneInput || !submitBtn) return;

    const phone = phoneInput.value.trim();
    const name = nameInput?.value.trim() || '';

    // Validate phone
    if (!phone || phone.length < 10) {
      phoneInput.classList.add('error');
      return;
    }
    phoneInput.classList.remove('error');

    this.state.phone = phone;
    this.state.name = name;

    // Disable submit button
    submitBtn.disabled = true;
    submitBtn.textContent = 'Обработка...';

    try {
      // Create pending booking
      const booking = await api.createBooking(
        this.state.reserveUuid,
        this.state.phone,
        this.state.name || undefined
      );

      this.state.bookingUuid = booking.uuid;
      this.stopReserveTimer();

      // Show pending state
      this.showStep('confirm');
      this.showPendingState();

      // Wait for confirmation
      const result = await api.waitForConfirmation(booking.uuid, 60, 1000);
      this.handleBookingResult(result);
    } catch (error: unknown) {
      console.error('Booking failed:', error);
      const message = error instanceof Error ? error.message : 'Ошибка бронирования';
      this.showErrorState(message);
    } finally {
      submitBtn.disabled = false;
      submitBtn.textContent = 'Записаться';
    }
  }

  private showPendingState(): void {
    document.getElementById('status-pending')?.classList.remove('hidden');
    document.getElementById('status-success')?.classList.add('hidden');
    document.getElementById('status-error')?.classList.add('hidden');
  }

  private handleBookingResult(result: PendingBooking): void {
    if (result.status === 'confirmed') {
      this.showSuccessState(result);
    } else {
      this.showErrorState(result.error || 'Не удалось подтвердить запись');
    }
  }

  private showSuccessState(booking: PendingBooking): void {
    document.getElementById('status-pending')?.classList.add('hidden');
    document.getElementById('status-error')?.classList.add('hidden');
    document.getElementById('status-success')?.classList.remove('hidden');

    // Fill summary
    const summary = document.getElementById('booking-summary');
    if (summary && this.state.service) {
      const date = new Date(this.state.date);
      const dateStr = date.toLocaleDateString('ru-RU', {
        weekday: 'long',
        day: 'numeric',
        month: 'long'
      });

      summary.innerHTML = `
        <div class="summary-row">
          <span class="summary-label">Услуга</span>
          <span class="summary-value">${this.escapeHtml(this.state.service.name)}</span>
        </div>
        <div class="summary-row">
          <span class="summary-label">Дата</span>
          <span class="summary-value">${dateStr}</span>
        </div>
        <div class="summary-row">
          <span class="summary-label">Время</span>
          <span class="summary-value">${this.state.time}</span>
        </div>
        ${this.state.specialist ? `
        <div class="summary-row">
          <span class="summary-label">Специалист</span>
          <span class="summary-value">${this.escapeHtml(this.state.specialist.name)}</span>
        </div>
        ` : ''}
        <div class="summary-row">
          <span class="summary-label">Стоимость</span>
          <span class="summary-value">${this.formatPrice(this.state.service.price)}</span>
        </div>
      `;
    }
  }

  private showErrorState(message: string): void {
    document.getElementById('status-pending')?.classList.add('hidden');
    document.getElementById('status-success')?.classList.add('hidden');
    document.getElementById('status-error')?.classList.remove('hidden');

    const errorMsg = document.getElementById('error-message');
    if (errorMsg) {
      errorMsg.textContent = message;
    }
  }

  private showError(message: string): void {
    // Simple alert for now
    alert(message);
  }

  private reset(): void {
    this.cancelReservation();

    this.state = {
      locationId: this.state.locationId,
      service: null,
      specialist: null,
      date: '',
      time: '',
      phone: '',
      name: '',
      reserveUuid: '',
      bookingUuid: '',
    };

    this.showStep('service');
  }

  // ──────────────────────────────────────────────────────────────────────────────
  // Helpers
  // ──────────────────────────────────────────────────────────────────────────────

  private escapeHtml(text: string): string {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  private formatPrice(price: number): string {
    return new Intl.NumberFormat('ru-RU', {
      style: 'currency',
      currency: 'RUB',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(price);
  }
}

// Initialize app when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
  new BookingApp();
});
