import argparse
import random
import sys

import pygame


WINDOW_SIZE = (1100, 700)
ROAD_RECT = pygame.Rect(70, 120, 960, 470)
BACKGROUND = (24, 29, 38)
ROAD = (49, 58, 69)
ROAD_EDGE = (130, 143, 157)
TEXT = (235, 240, 245)
ARRIVAL = (76, 190, 232)
PARKED = (244, 177, 68)
LEAVING = (116, 215, 133)
PERSON = (250, 245, 230)
GATE = (220, 95, 95)
PERSON_WALK_MINUTES = 2.0
START_TIME_MINUTES = 8 * 60 + 30


def format_clock_time(elapsed_minutes):
    absolute_minutes = START_TIME_MINUTES + elapsed_minutes
    hour = int(absolute_minutes // 60) % 24
    minute = int(absolute_minutes % 60)
    return f"{hour:02d}:{minute:02d}"


class Car:
    def __init__(self, arrival_time, parking_duration, x, y):
        self.arrival_time = arrival_time
        self.parking_duration = parking_duration
        self.x = x
        self.y = y
        self.state = "arriving"
        self.parked_at = None
        self.leaving_at = None

    def update(self, elapsed, gate_open, gate_close):
        if self.state == "arriving" and elapsed >= self.arrival_time:
            self.state = "waiting" if elapsed < gate_open else "parked"
            if self.state == "parked":
                self.parked_at = elapsed
        elif self.state == "waiting" and elapsed >= gate_open:
            self.state = "parked"
            self.parked_at = elapsed
        elif self.state == "parked" and elapsed >= self.parked_at + self.parking_duration:
            self.state = "leaving"
            self.leaving_at = elapsed
        elif self.state == "leaving" and elapsed >= self.leaving_at + PERSON_WALK_MINUTES:
            self.state = "gone"

        if self.state == "waiting" and elapsed >= gate_close:
            self.state = "parked"
            self.parked_at = elapsed


def build_cars(total_cars, simulation_duration, gate_open, gate_close,
               arrival_window, drop_lower, drop_upper):
    arrival_start = max(0, gate_open - arrival_window)
    arrivals = sorted(random.uniform(arrival_start, gate_close)
                      for _ in range(total_cars))
    cars = []
    for index, arrival in enumerate(arrivals):
        x = ROAD_RECT.left + 30 + (index % 12) * 75
        y = ROAD_RECT.top + 65 + (index // 12) * 48
        cars.append(Car(arrival, random.uniform(drop_lower, drop_upper), x, y))
    return cars


def draw_car(screen, car, elapsed):
    colour = {
        "arriving": ARRIVAL,
        "waiting": ARRIVAL,
        "parked": PARKED,
        "leaving": LEAVING,
    }.get(car.state, PARKED)
    car_rect = pygame.Rect(int(car.x - 22), int(car.y - 12), 44, 24)
    pygame.draw.rect(screen, colour, car_rect, border_radius=5)
    pygame.draw.rect(screen, (235, 240, 245), car_rect, width=2, border_radius=5)
    pygame.draw.line(
        screen, (235, 240, 245),
        (int(car.x - 8), int(car.y - 12)),
        (int(car.x - 8), int(car.y + 12)), width=2)

    if car.state == "leaving":
        progress = min(1.0, (elapsed - car.leaving_at) / PERSON_WALK_MINUTES)
        person_x = car.x + (GATE_X - car.x) * progress
        pygame.draw.circle(screen, PERSON, (int(person_x), int(car.y)), 6)


GATE_X = ROAD_RECT.right - 28


def draw_gate(screen):
    pygame.draw.line(
        screen, GATE, (GATE_X, ROAD_RECT.top),
        (GATE_X, ROAD_RECT.bottom), width=8)
    gate_label = pygame.font.Font(None, 24).render("GATE", True, GATE)
    screen.blit(gate_label, (GATE_X - 28, ROAD_RECT.top - 28))


def main():
    parser = argparse.ArgumentParser(description="Live pygame school drop-off visualization")
    parser.add_argument("--cars", type=int, default=70)
    parser.add_argument("--duration", type=float, default=120)
    parser.add_argument("--gate-open", type=float, default=30)
    parser.add_argument("--gate-close", type=float, default=35)
    parser.add_argument("--arrival-window", type=float, default=10)
    parser.add_argument("--drop-lower", type=float, default=1.0)
    parser.add_argument("--drop-upper", type=float, default=3.0)
    args = parser.parse_args()

    if args.cars < 1 or args.gate_open >= args.gate_close:
        parser.error("cars must be positive and gate-open must be before gate-close")

    pygame.init()
    screen = pygame.display.set_mode(WINDOW_SIZE)
    pygame.display.set_caption("School Drop-Off Parking Visualization")
    font = pygame.font.Font(None, 30)
    small_font = pygame.font.Font(None, 24)
    clock = pygame.time.Clock()
    elapsed = 0.0
    time_scale = 3.0
    cars = build_cars(
        args.cars, args.duration, args.gate_open, args.gate_close,
        args.arrival_window, args.drop_lower, args.drop_upper)

    running = True
    while running:
        frame_seconds = clock.tick(60) / 1000
        elapsed += frame_seconds * time_scale
        if elapsed > args.duration:
            elapsed = 0
            cars = build_cars(
                args.cars, args.duration, args.gate_open, args.gate_close,
                args.arrival_window, args.drop_lower, args.drop_upper)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_SPACE:
                elapsed = 0
                cars = build_cars(
                    args.cars, args.duration, args.gate_open, args.gate_close,
                    args.arrival_window, args.drop_lower, args.drop_upper)

        for car in cars:
            car.update(elapsed, args.gate_open, args.gate_close)

        screen.fill(BACKGROUND)
        pygame.draw.rect(screen, ROAD, ROAD_RECT, border_radius=8)
        pygame.draw.rect(screen, ROAD_EDGE, ROAD_RECT, width=3, border_radius=8)
        draw_gate(screen)

        title = font.render("School Drop-Off Parking", True, TEXT)
        screen.blit(title, (70, 45))
        status = small_font.render(
            f"Time: {format_clock_time(elapsed)}   "
            f"Gate: {format_clock_time(args.gate_open)}-"
            f"{format_clock_time(args.gate_close)}   "
            f"Parked: {sum(car.state == 'parked' for car in cars)}",
            True, TEXT)
        screen.blit(status, (70, 82))

        for car in cars:
            if car.state != "gone" and elapsed >= car.arrival_time:
                draw_car(screen, car, elapsed)

        legend = small_font.render(
            "Blue: arriving/waiting   Gold: parked   Green: leaving   White dot: person",
            True, TEXT)
        screen.blit(legend, (70, 625))
        pygame.display.flip()

    pygame.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
