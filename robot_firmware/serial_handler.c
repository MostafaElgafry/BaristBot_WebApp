/**
 * BaristBot Robot Serial Communication Handler
 *
 * Protocol:
 *   App -> Robot: JOB,{dose},{grade},{recipe}\n  (e.g., JOB,18.50,5,2\n)
 *   Robot -> App: ACK\n  (when job received and started)
 *   Robot -> App: OK\n   (when job completed)
 *   Robot -> App: ERR:{message}\n (on error)
 */

#include <stdio.h>
#include <string.h>
#include <stdlib.h>

// ============================================================================
// Configuration
// ============================================================================

#define RX_BUFFER_SIZE 64
#define SERIAL_BAUD_RATE 115200

// ============================================================================
// Data Structures
// ============================================================================

typedef struct {
    float dose_grams;      // 0.1 - 200.0 grams
    int grind_grade;       // 1 - 10
    int recipe_number;     // 1 - 4
    int is_valid;
} JobCommand;

typedef enum {
    ROBOT_IDLE,
    ROBOT_PROCESSING,
    ROBOT_ERROR
} RobotState;

// ============================================================================
// Global Variables
// ============================================================================

static char rx_buffer[RX_BUFFER_SIZE];
static int rx_index = 0;
static RobotState robot_state = ROBOT_IDLE;
static JobCommand current_job = {0};

// ============================================================================
// Serial Communication (IMPLEMENT FOR YOUR PLATFORM)
// ============================================================================

/**
 * Send a string over serial UART
 * Replace with your platform-specific implementation
 */
void serial_send(const char* message) {
    // ===== IMPLEMENT FOR YOUR PLATFORM =====
    //
    // STM32 HAL:
    //   HAL_UART_Transmit(&huart1, (uint8_t*)message, strlen(message), 100);
    //
    // Arduino:
    //   Serial.print(message);
    //
    // AVR:
    //   while (*message) {
    //       while (!(UCSR0A & (1 << UDRE0)));
    //       UDR0 = *message++;
    //   }
    //
    // For testing (printf):
    printf("%s", message);
}

/**
 * Send formatted response
 */
void send_ack(void) {
    serial_send("ACK\n");
}

void send_ok(void) {
    serial_send("OK\n");
}

void send_done(void) {
    serial_send("DONE\n");
}

void send_error(const char* error_msg) {
    serial_send("ERR:");
    serial_send(error_msg);
    serial_send("\n");
}

// ============================================================================
// Command Parsing
// ============================================================================

/**
 * Parse JOB command: JOB,18.50,5,2
 * Returns JobCommand with is_valid = 1 if successful
 */
JobCommand parse_job_command(char* cmd) {
    JobCommand job = {0.0f, 0, 0, 0};

    // Check if starts with "JOB,"
    if (strncmp(cmd, "JOB,", 4) != 0) {
        return job;  // Invalid format
    }

    // Create a copy for parsing (strtok modifies the string)
    char cmd_copy[RX_BUFFER_SIZE];
    strncpy(cmd_copy, cmd + 4, RX_BUFFER_SIZE - 1);
    cmd_copy[RX_BUFFER_SIZE - 1] = '\0';

    // Parse: dose,grade,recipe
    char* token = strtok(cmd_copy, ",");
    if (token) {
        job.dose_grams = (float)atof(token);

        token = strtok(NULL, ",");
        if (token) {
            job.grind_grade = atoi(token);

            token = strtok(NULL, ",\n\r");
            if (token) {
                job.recipe_number = atoi(token);
                job.is_valid = 1;
            }
        }
    }

    // Validate parameter ranges
    if (job.dose_grams < 0.1f || job.dose_grams > 200.0f) {
        job.is_valid = 0;
    }
    if (job.grind_grade < 1 || job.grind_grade > 10) {
        job.is_valid = 0;
    }
    if (job.recipe_number < 1 || job.recipe_number > 4) {
        job.is_valid = 0;
    }

    return job;
}

// ============================================================================
// Job Execution (IMPLEMENT YOUR COFFEE MAKING LOGIC)
// ============================================================================

/**
 * Execute the coffee making job
 * IMPLEMENT THIS FUNCTION WITH YOUR ACTUAL HARDWARE CONTROL
 */
void execute_job(JobCommand* job) {
    // ===== IMPLEMENT YOUR COFFEE MAKING LOGIC HERE =====
    //
    // Example steps:
    // 1. Set grinder to job->grind_grade
    // 2. Grind job->dose_grams of coffee
    // 3. Execute recipe job->recipe_number
    // 4. Wait for completion
    //
    // Example:
    //   set_grinder_grade(job->grind_grade);
    //   grind_coffee(job->dose_grams);
    //   run_recipe(job->recipe_number);
    //   wait_for_brew_complete();

    // Placeholder: simulate work with delay
    // Replace with actual implementation
    // delay_ms(5000);  // Simulate 5 second job
}

// ============================================================================
// Command Processing
// ============================================================================

/**
 * Process a complete command received from serial
 */
void process_command(char* cmd) {
    // Trim newline/carriage return
    cmd[strcspn(cmd, "\r\n")] = '\0';

    // Skip empty commands
    if (strlen(cmd) == 0) {
        return;
    }

    // ----- Handle JOB command -----
    if (strncmp(cmd, "JOB,", 4) == 0) {
        // Don't accept new job if already processing
        if (robot_state == ROBOT_PROCESSING) {
            send_error("BUSY");
            return;
        }

        // Parse the job command
        JobCommand job = parse_job_command(cmd);

        if (job.is_valid) {
            // Store current job
            current_job = job;
            robot_state = ROBOT_PROCESSING;

            // Send ACK immediately (job received, starting)
            send_ack();

            // Execute the job
            execute_job(&job);

            // Job completed - send OK
            robot_state = ROBOT_IDLE;
            send_ok();

        } else {
            send_error("INVALID_PARAMS");
        }
    }
    // ----- Handle STATUS command (optional) -----
    else if (strcmp(cmd, "STATUS") == 0) {
        switch (robot_state) {
            case ROBOT_IDLE:
                serial_send("IDLE\n");
                break;
            case ROBOT_PROCESSING:
                serial_send("PROCESSING\n");
                break;
            case ROBOT_ERROR:
                serial_send("ERROR\n");
                break;
        }
    }
    // ----- Handle PING command (optional) -----
    else if (strcmp(cmd, "PING") == 0) {
        serial_send("PONG\n");
    }
    // ----- Handle STOP command (optional) -----
    else if (strcmp(cmd, "STOP") == 0) {
        // Emergency stop - implement your stop logic
        robot_state = ROBOT_IDLE;
        send_ok();
    }
    // ----- Unknown command -----
    else {
        send_error("UNKNOWN_CMD");
    }
}

// ============================================================================
// Serial Receive Handler
// ============================================================================

/**
 * Call this function when a byte is received from UART
 * Can be called from interrupt or polling loop
 */
void on_serial_byte_received(char c) {
    // End of command (newline)
    if (c == '\n' || c == '\r') {
        if (rx_index > 0) {
            rx_buffer[rx_index] = '\0';
            process_command(rx_buffer);
            rx_index = 0;
        }
    }
    // Add character to buffer
    else if (rx_index < RX_BUFFER_SIZE - 1) {
        rx_buffer[rx_index++] = c;
    }
    // Buffer overflow - reset
    else {
        rx_index = 0;
    }
}

// ============================================================================
// Platform-Specific Integration Examples
// ============================================================================

#ifdef STM32_HAL
/*
 * STM32 HAL Integration Example
 *
 * In main.c, enable UART receive interrupt:
 *   uint8_t rx_byte;
 *   HAL_UART_Receive_IT(&huart1, &rx_byte, 1);
 *
 * Implement callback:
 */
uint8_t uart_rx_byte;

void HAL_UART_RxCpltCallback(UART_HandleTypeDef *huart) {
    if (huart->Instance == USART1) {
        on_serial_byte_received((char)uart_rx_byte);
        HAL_UART_Receive_IT(huart, &uart_rx_byte, 1);
    }
}

void serial_send(const char* message) {
    HAL_UART_Transmit(&huart1, (uint8_t*)message, strlen(message), 100);
}
#endif

#ifdef ARDUINO
/*
 * Arduino Integration Example
 *
 * void setup() {
 *     Serial.begin(115200);
 * }
 *
 * void loop() {
 *     while (Serial.available()) {
 *         on_serial_byte_received(Serial.read());
 *     }
 * }
 */
void serial_send(const char* message) {
    Serial.print(message);
}
#endif

// ============================================================================
// Test Main (for PC testing)
// ============================================================================

#ifndef STM32_HAL
#ifndef ARDUINO

int main(void) {
    printf("BaristBot Serial Handler Test\n");
    printf("==============================\n\n");

    // Test 1: Valid JOB command
    printf("Test 1: JOB,18.50,5,2\n");
    const char* test1 = "JOB,18.50,5,2\n";
    for (int i = 0; test1[i]; i++) {
        on_serial_byte_received(test1[i]);
    }
    printf("\n");

    // Test 2: Invalid parameters
    printf("Test 2: JOB,999,99,99 (invalid)\n");
    const char* test2 = "JOB,999,99,99\n";
    for (int i = 0; test2[i]; i++) {
        on_serial_byte_received(test2[i]);
    }
    printf("\n");

    // Test 3: STATUS command
    printf("Test 3: STATUS\n");
    const char* test3 = "STATUS\n";
    for (int i = 0; test3[i]; i++) {
        on_serial_byte_received(test3[i]);
    }
    printf("\n");

    // Test 4: Unknown command
    printf("Test 4: HELLO (unknown)\n");
    const char* test4 = "HELLO\n";
    for (int i = 0; test4[i]; i++) {
        on_serial_byte_received(test4[i]);
    }
    printf("\n");

    return 0;
}

#endif
#endif
