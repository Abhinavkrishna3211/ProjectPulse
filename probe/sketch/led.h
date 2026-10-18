#pragma once

// RGB status LED (common anode): blue = learning/pairing, green = OK,
// amber = watch, red = stop/fault. Call once from setup(), after Bridge.begin().
void led_start();
