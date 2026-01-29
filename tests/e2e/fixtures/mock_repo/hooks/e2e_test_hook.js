#!/usr/bin/env node
/**
 * E2E test JavaScript hook script for validation.
 *
 * This hook is triggered by PostToolUse events for Read operations.
 * Validates that JavaScript hooks receive proper node prefix.
 */

'use strict';

function main() {
    // Read stdin (Claude Code passes event data via stdin)
    let inputData = '';

    process.stdin.setEncoding('utf8');
    process.stdin.on('readable', () => {
        let chunk;
        while ((chunk = process.stdin.read()) !== null) {
            inputData += chunk;
        }
    });

    process.stdin.on('end', () => {
        let event = {};
        try {
            event = inputData.trim() ? JSON.parse(inputData) : {};
        } catch (e) {
            event = {};
        }

        const result = {
            continue: true,
            message: 'E2E JavaScript hook (.js) executed successfully',
            runtime: 'node',
            event_type: event.type || 'unknown',
        };

        console.log(JSON.stringify(result));
    });
}

main();
