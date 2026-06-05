package com.example.scannerfeature.backend.dto;

import java.time.OffsetDateTime;

public record StorageResult(
        String storedFileName,
        String storedPath,
        String contentType,
        long fileSize,
        OffsetDateTime storedAt
) {
}
