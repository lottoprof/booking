// frontend/ts/miniapp.ts
/**
 * Telegram Mini App for booking
 *
 * This is a TRUSTED flow:
 * - initData is verified by Gateway
 * - User identity is known from Telegram
 * - No phone input required
 * - Uses /api/* endpoints (proxied to Backend)
 *
 * Flow:
 * 1. Service selection
 * 2. Calendar (date selection)
 * 3. Time selection
 * 4. Confirmation (direct booking via API)
 */

export {}; // Make this a module

// Declare Telegram WebApp types
declare global {
  interface Window {
    Telegram: {
      WebApp: TelegramWebApp;
    };
  }
}

interface TelegramWebApp {
  ready: () => void;
  close: () => void;
  expand: () => void;
  MainButton: {
    text: string;
    color: string;
    textColor: string;
    isVisible: boolean;
    isActive: boolean;
    isProgressVisible: boolean;
    show: () => void;
    hide: () => void;
    enable: () => void;
    disable: () => void;
    showProgress: (leaveActive?: boolean) => void;
    hideProgress: () => void;
    onClick: (callback: () => void) => void;
    offClick: (callback: () => void) => void;
  };
  BackButton: {
    isVisible: boolean;
    show: () => void;
    hide: () => void;
    onClick: (callback: () => void) => void;
    offClick: (callback: () => void) => void;
  };
  initData: string;
  initDataUnsafe: {
    user?: {
      id: number;
      first_name: string;
      last_name?: string;
      username?: string;
    };
  };
  themeParams: {
    bg_color?: string;
    text_color?: string;
    hint_color?: string;
    link_color?: string;
    button_color?: string;
    button_text_color?: string;
    secondary_bg_color?: string;
  };
  HapticFeedback: {
    impactOccurred: (style: 'light' | 'medium' | 'heavy' | 'rigid' | 'soft') => void;
    notificationOccurred: (type: 'error' | 'success' | 'warning') => void;
    selectionChanged: () => void;
  };
}

// Types for API responses
interface Service {
  id: number;
  name: string;
  description: string | null;
  category: string | null;
  duration_min: number;
  break_min: number;
  price: number;
}

interface Location {
  id: number;
  name: string;
}

interface DayStatus {
  date: string;
  has_slots: boolean;
  open_slots_count: number;
}

interface TimeSlot {
  time: string;
  specialists: Array<{ id: number; name: string }>;
}

interface DayResponse {
  available_times: TimeSlot[];
}

interface BookingCreate {
  company_id: number;
  location_id: number;
  service_id: number;
  client_id: number;
  specialist_id: number;
  date_start: string;
  date_end: string;
  duration_minutes: number;
  break_minutes: number;
}

// State
type Step = 'service' | 'calendar' | 'time' | 'confirm';

interface AppState {
  locationId: number;
  clientId: number;
  service: Service | null;
  date: string;
  time: string;
  specialistId: number | null;
}

class MiniApp {
  private tg: TelegramWebApp;
  private state: AppState = {
    locationId: 1,
    clientId: 0,
    service: null,
    date: '',
    time: '',
    specialistId: null,
  };

  private services: Service[] = [];
  private availableDays: Map<string, boolean> = new Map();
  private timeSlots: TimeSlot[] = [];
  private currentMonth: Date = new Date();
  private currentStep: Step = 'service';
  private mainButtonCallback: (() => void) | null = null;

  constructor() {
    this.tg = window.Telegram.WebApp;
    this.init();
  }

  private async init(): Promise<void> {
    // Telegram WebApp setup
    this.tg.ready();
    this.tg.expand();

    // Setup back button
    this.tg.BackButton.onClick(() => this.handleBack());

    try {
      // Verify initData and get user
      const userData = await this.verifyUser();
      this.state.clientId = userData.client_id;

      // Load locations
      const locations = await this.fetchAPI<Location[]>('/locations');
      if (locations.length > 0) {
        this.state.locationId = locations[0].id;
      }

      // Load services
      this.services = await this.fetchAPI<Service[]>('/services');

      // Show app
      this.hideLoading();
      this.renderServices();
      this.showStep('service');
    } catch (error) {
      console.error('Init error:', error);
      this.showInitError(error instanceof Error ? error.message : 'Unknown error');
    }
  }

  // ──────────────────────────────────────────────────────────────────────────────
  // API
  // ──────────────────────────────────────────────────────────────────────────────

  private async fetchAPI<T>(endpoint: string, options?: RequestInit): Promise<T> {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    };

    // Add initData for authentication
    if (this.tg.initData) {
      headers['X-Telegram-Init-Data'] = this.tg.initData;
    }

    const response = await fetch(endpoint, {
      ...options,
      headers: {
        ...headers,
        ...options?.headers,
      },
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(error.detail || `API error: ${response.status}`);
    }

    return response.json();
  }

  private async verifyUser(): Promise<{ client_id: number }> {
    // The gateway verifies initData and returns user info
    // For Mini App, we get client_id from the authenticated user
    const user = this.tg.initDataUnsafe.user;
    if (!user) {
      throw new Error('User not found in initData');
    }

    // Get or create user by tg_id
    try {
      const userData = await this.fetchAPI<{ id: number }>(`/users/by_tg/${user.id}`);
      return { client_id: userData.id };
    } catch {
      // User might not exist yet - this is handled by backend
      throw new Error('Please register through the bot first');
    }
  }

  // ──────────────────────────────────────────────────────────────────────────────
  // UI
  // ──────────────────────────────────────────────────────────────────────────────

  private hideLoading(): void {
    document.getElementById('loading-screen')?.classList.add('hidden');
    document.getElementById('app-container')?.classList.remove('hidden');
  }

  private showInitError(message: string): void {
    document.getElementById('loading-screen')?.classList.add('hidden');
    document.getElementById('error-screen')?.classList.remove('hidden');
    const errorMsg = document.getElementById('init-error-message');
    if (errorMsg) errorMsg.textContent = message;
  }

  private showStep(step: Step): void {
    // Hide all steps
    document.querySelectorAll('.step').forEach((el) => el.classList.remove('active'));

    // Show current step
    document.getElementById(`step-${step}`)?.classList.add('active');

    // Update progress
    const stepOrder: Step[] = ['service', 'calendar', 'time', 'confirm'];
    const stepIndex = stepOrder.indexOf(step);
    document.querySelectorAll('.progress-step').forEach((el, i) => {
      el.classList.remove('completed', 'active');
      if (i < stepIndex) el.classList.add('completed');
      else if (i === stepIndex) el.classList.add('active');
    });

    // Back button
    if (step === 'service') {
      this.tg.BackButton.hide();
    } else {
      this.tg.BackButton.show();
    }

    // Main button
    this.updateMainButton(step);

    this.currentStep = step;
  }

  private updateMainButton(step: Step): void {
    // Remove old callback
    if (this.mainButtonCallback) {
      this.tg.MainButton.offClick(this.mainButtonCallback);
      this.mainButtonCallback = null;
    }

    switch (step) {
      case 'confirm':
        this.tg.MainButton.hide();
        break;
      default:
        this.tg.MainButton.hide();
        break;
    }
  }

  private handleBack(): void {
    this.tg.HapticFeedback.selectionChanged();

    switch (this.currentStep) {
      case 'calendar':
        this.showStep('service');
        break;
      case 'time':
        this.showStep('calendar');
        break;
      case 'confirm':
        this.showStep('time');
        break;
    }
  }

  // ──────────────────────────────────────────────────────────────────────────────
  // Services
  // ──────────────────────────────────────────────────────────────────────────────

  private renderServices(): void {
    const container = document.getElementById('services-list');
    if (!container) return;

    container.innerHTML = this.services
      .map(
        (s) => `
      <div class="service-card" data-id="${s.id}">
        <div class="flex justify-between items-start">
          <div>
            <div class="name">${this.escapeHtml(s.name)}</div>
            <div class="details text-hint text-sm">${s.duration_min} мин</div>
          </div>
          <div class="price">${this.formatPrice(s.price)}</div>
        </div>
      </div>
    `
      )
      .join('');

    // Click handler
    container.addEventListener('click', (e) => {
      const card = (e.target as HTMLElement).closest('.service-card');
      if (card) {
        const id = parseInt(card.getAttribute('data-id') || '0');
        this.selectService(id);
      }
    });
  }

  private async selectService(id: number): Promise<void> {
    const service = this.services.find((s) => s.id === id);
    if (!service) return;

    this.tg.HapticFeedback.selectionChanged();
    this.state.service = service;

    // Highlight
    document.querySelectorAll('.service-card').forEach((el) => {
      el.classList.remove('selected');
      if (el.getAttribute('data-id') === String(id)) {
        el.classList.add('selected');
      }
    });

    // Load calendar
    await this.loadCalendar();
  }

  // ──────────────────────────────────────────────────────────────────────────────
  // Calendar
  // ──────────────────────────────────────────────────────────────────────────────

  private async loadCalendar(): Promise<void> {
    if (!this.state.service) return;

    try {
      const response = await this.fetchAPI<{ days: DayStatus[] }>(
        `/slots/calendar?location_id=${this.state.locationId}&start_date=&end_date=`
      );

      this.availableDays.clear();
      for (const day of response.days) {
        this.availableDays.set(day.date, day.has_slots);
      }

      const firstAvailable = response.days.find((d) => d.has_slots);
      if (firstAvailable) {
        this.currentMonth = new Date(firstAvailable.date);
      }

      this.renderCalendar();
      this.showStep('calendar');
    } catch (error) {
      console.error('Failed to load calendar:', error);
      this.tg.HapticFeedback.notificationOccurred('error');
    }
  }

  private renderCalendar(): void {
    const container = document.getElementById('calendar-days');
    const monthDisplay = document.getElementById('current-month');
    if (!container || !monthDisplay) return;

    const year = this.currentMonth.getFullYear();
    const month = this.currentMonth.getMonth();

    const monthNames = [
      'Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
      'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь'
    ];
    monthDisplay.textContent = `${monthNames[month]} ${year}`;

    const firstDay = new Date(year, month, 1);
    const lastDay = new Date(year, month + 1, 0);
    const startOffset = (firstDay.getDay() + 6) % 7;

    const today = new Date();
    today.setHours(0, 0, 0, 0);

    let html = '';
    for (let i = 0; i < startOffset; i++) {
      html += '<div class="calendar-day empty"></div>';
    }

    for (let day = 1; day <= lastDay.getDate(); day++) {
      const date = new Date(year, month, day);
      const dateStr = date.toISOString().split('T')[0];
      const isPast = date < today;
      const isToday = date.getTime() === today.getTime();
      const isAvailable = !isPast && this.availableDays.get(dateStr);

      const classes = ['calendar-day'];
      if (isToday) classes.push('today');
      if (isAvailable) classes.push('available');
      if (!isAvailable || isPast) classes.push('unavailable');

      html += `<div class="${classes.join(' ')}" data-date="${dateStr}">${day}</div>`;
    }

    container.innerHTML = html;

    // Click handler
    container.addEventListener('click', (e) => {
      const day = (e.target as HTMLElement).closest('.calendar-day');
      if (day?.classList.contains('available')) {
        const date = day.getAttribute('data-date');
        if (date) this.selectDate(date);
      }
    });

    // Nav buttons
    document.getElementById('prev-month')?.addEventListener('click', () => {
      this.currentMonth.setMonth(this.currentMonth.getMonth() - 1);
      this.renderCalendar();
    });

    document.getElementById('next-month')?.addEventListener('click', () => {
      this.currentMonth.setMonth(this.currentMonth.getMonth() + 1);
      this.renderCalendar();
    });
  }

  private async selectDate(date: string): Promise<void> {
    this.tg.HapticFeedback.selectionChanged();
    this.state.date = date;

    document.querySelectorAll('.calendar-day').forEach((el) => {
      el.classList.remove('selected');
      if (el.getAttribute('data-date') === date) {
        el.classList.add('selected');
      }
    });

    await this.loadTimeSlots();
  }

  // ──────────────────────────────────────────────────────────────────────────────
  // Time Slots
  // ──────────────────────────────────────────────────────────────────────────────

  private async loadTimeSlots(): Promise<void> {
    if (!this.state.service) return;

    try {
      const response = await this.fetchAPI<DayResponse>(
        `/slots/day?location_id=${this.state.locationId}&service_id=${this.state.service.id}&date=${this.state.date}`
      );

      this.timeSlots = response.available_times;
      this.renderTimeSlots();

      const dateDisplay = document.getElementById('selected-date-display');
      if (dateDisplay) {
        const d = new Date(this.state.date);
        dateDisplay.textContent = d.toLocaleDateString('ru-RU', {
          weekday: 'long',
          day: 'numeric',
          month: 'long'
        });
      }

      this.showStep('time');
    } catch (error) {
      console.error('Failed to load time slots:', error);
      this.tg.HapticFeedback.notificationOccurred('error');
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
      .map((slot) => `<div class="time-slot" data-time="${slot.time}">${slot.time}</div>`)
      .join('');

    container.addEventListener('click', (e) => {
      const slot = (e.target as HTMLElement).closest('.time-slot');
      if (slot) {
        const time = slot.getAttribute('data-time');
        if (time) this.selectTime(time);
      }
    });
  }

  private async selectTime(time: string): Promise<void> {
    this.tg.HapticFeedback.selectionChanged();

    const slot = this.timeSlots.find((s) => s.time === time);
    if (!slot) return;

    this.state.time = time;
    if (slot.specialists.length > 0) {
      this.state.specialistId = slot.specialists[0].id;
    }

    document.querySelectorAll('.time-slot').forEach((el) => {
      el.classList.remove('selected');
      if (el.getAttribute('data-time') === time) {
        el.classList.add('selected');
      }
    });

    // Create booking
    await this.createBooking();
  }

  // ──────────────────────────────────────────────────────────────────────────────
  // Booking
  // ──────────────────────────────────────────────────────────────────────────────

  private async createBooking(): Promise<void> {
    if (!this.state.service || !this.state.specialistId) return;

    this.showStep('confirm');
    this.showPendingState();

    try {
      const dateStart = new Date(`${this.state.date}T${this.state.time}:00`);
      const dateEnd = new Date(dateStart.getTime() + this.state.service.duration_min * 60000);

      const bookingData: BookingCreate = {
        company_id: 1, // Default company
        location_id: this.state.locationId,
        service_id: this.state.service.id,
        client_id: this.state.clientId,
        specialist_id: this.state.specialistId,
        date_start: dateStart.toISOString().replace('T', ' ').split('.')[0],
        date_end: dateEnd.toISOString().replace('T', ' ').split('.')[0],
        duration_minutes: this.state.service.duration_min,
        break_minutes: this.state.service.break_min || 0,
      };

      const result = await this.fetchAPI<{ id: number }>('/bookings', {
        method: 'POST',
        body: JSON.stringify(bookingData),
      });

      this.tg.HapticFeedback.notificationOccurred('success');
      this.showSuccessState(result.id);
    } catch (error) {
      console.error('Booking failed:', error);
      this.tg.HapticFeedback.notificationOccurred('error');
      this.showErrorState(error instanceof Error ? error.message : 'Unknown error');
    }
  }

  private showPendingState(): void {
    document.getElementById('status-pending')?.classList.remove('hidden');
    document.getElementById('status-success')?.classList.add('hidden');
    document.getElementById('status-error')?.classList.add('hidden');
  }

  private showSuccessState(bookingId: number): void {
    document.getElementById('status-pending')?.classList.add('hidden');
    document.getElementById('status-error')?.classList.add('hidden');
    document.getElementById('status-success')?.classList.remove('hidden');

    const summary = document.getElementById('booking-summary');
    if (summary && this.state.service) {
      const d = new Date(this.state.date);
      summary.innerHTML = `
        <div class="summary-row">
          <span class="summary-label text-hint">Услуга</span>
          <span class="summary-value">${this.escapeHtml(this.state.service.name)}</span>
        </div>
        <div class="summary-row">
          <span class="summary-label text-hint">Дата</span>
          <span class="summary-value">${d.toLocaleDateString('ru-RU')}</span>
        </div>
        <div class="summary-row">
          <span class="summary-label text-hint">Время</span>
          <span class="summary-value">${this.state.time}</span>
        </div>
        <div class="summary-row">
          <span class="summary-label text-hint">Стоимость</span>
          <span class="summary-value">${this.formatPrice(this.state.service.price)}</span>
        </div>
      `;
    }

    // Show close button
    this.tg.MainButton.text = 'Закрыть';
    this.tg.MainButton.show();
    this.mainButtonCallback = () => this.tg.close();
    this.tg.MainButton.onClick(this.mainButtonCallback);
  }

  private showErrorState(message: string): void {
    document.getElementById('status-pending')?.classList.add('hidden');
    document.getElementById('status-success')?.classList.add('hidden');
    document.getElementById('status-error')?.classList.remove('hidden');

    const errorMsg = document.getElementById('error-message');
    if (errorMsg) errorMsg.textContent = message;

    // Show retry button
    this.tg.MainButton.text = 'Попробовать снова';
    this.tg.MainButton.show();
    this.mainButtonCallback = () => {
      this.showStep('time');
    };
    this.tg.MainButton.onClick(this.mainButtonCallback);
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
    }).format(price);
  }
}

// Initialize when DOM ready
document.addEventListener('DOMContentLoaded', () => {
  new MiniApp();
});
