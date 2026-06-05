package com.example.scannerfeature.backend.dto;

import java.time.OffsetDateTime;

public record StoredDocumentSummary(
        String storedFileName,
        String contentType,
        long fileSize,
        OffsetDateTime storedAt
) {
}
