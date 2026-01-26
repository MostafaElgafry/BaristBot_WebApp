/**
 * BaristBot Robot Serial Communication Handler
 * Header File
 */

#ifndef SERIAL_HANDLER_H
#define SERIAL_HANDLER_H

#ifdef __cplusplus
extern "C" {
#endif

// ============================================================================
// Data Structures
// ============================================================================

typedef struct {
    int dose_grams;        // 1 - 200 grams (integer)
    int grind_grade;       // 1 - 11
    int doser_number;      // 1 - 4
    int recipe_number;     // 1 - 4
    int is_valid;
} JobCommand;

typedef enum {
    ROBOT_IDLE,
    ROBOT_PROCESSING,
    ROBOT_ERROR
} RobotState;

// ============================================================================
// Public Functions
// ============================================================================

/**
 * Call this when a byte is received from UART
 * @param c The received character
 */
void on_serial_byte_received(char c);

/**
 * Send ACK response
 */
void send_ack(void);

/**
 * Send OK response (job completed)
 */
void send_ok(void);

/**
 * Send DONE response (alternative completion)
 */
void send_done(void);

/**
 * Send error response
 * @param error_msg Error message (e.g., "INVALID_PARAMS")
 */
void send_error(const char* error_msg);

// ============================================================================
// Platform-Specific (MUST BE IMPLEMENTED)
// ============================================================================

/**
 * Send a string over serial UART
 * MUST BE IMPLEMENTED for your platform
 * @param message Null-terminated string to send
 */
void serial_send(const char* message);

/**
 * Execute the coffee making job
 * MUST BE IMPLEMENTED with your hardware control logic
 * @param job Pointer to job parameters
 */
void execute_job(JobCommand* job);

#ifdef __cplusplus
}
#endif

#endif // SERIAL_HANDLER_H
