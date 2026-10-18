#pragma once

// Learn / ack button (D2, internal pull-up). Call button_start() once from
// setup(), then button_update() every loop() iteration (non-blocking).
void button_start();
void button_update();
