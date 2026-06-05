package com.example.scannerfeature.backend.service;

import com.example.scannerfeature.backend.dto.BackendHealthResponse;
import com.example.scannerfeature.backend.dto.StoredDocumentSummary;
import com.example.scannerfeature.backend.config.StorageProperties;
import com.example.scannerfeature.backend.dto.StorageResult;
import com.example.scannerfeature.backend.exception.InvalidUploadException;
import com.example.scannerfeature.backend.exception.StorageException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;
import org.springframework.web.multipart.MultipartFile;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.FileAlreadyExistsException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.regex.Pattern;
import java.util.stream.Stream;

@Service
public class DocumentStorageService {

    private static final Logger LOGGER = LoggerFactory.getLogger(DocumentStorageService.class);
    private static final Pattern INVALID_CHARS = Pattern.compile("[^a-zA-Z0-9._-]");
    private static final DateTimeFormatter TIMESTAMP_FORMATTER = DateTimeFormatter.ofPattern("yyyyMMdd-HHmmss");
    private static final Set<String> ALLOWED_CONTENT_TYPES = Set.of("image/png", "image/jpeg", "application/pdf");

    private final StorageProperties storageProperties;

    public DocumentStorageService(StorageProperties storageProperties) {
        this.storageProperties = storageProperties;
    }

    public StorageResult store(
            MultipartFile file,
            String originalFileName,
            String declaredContentType,
            Map<String, String> metadata) {

        String validatedContentType = validateUpload(file, originalFileName, declaredContentType);

        Path targetFolder = resolveTargetFolder();
        String sanitizedBaseName = sanitizeBaseName(originalFileName);
        String extension = determineExtension(validatedContentType);
        String timestamp = LocalDateTime.now().format(TIMESTAMP_FORMATTER);

        for (int counter = 0; ; counter++) {
            Path targetFile = buildTargetFilePath(targetFolder, sanitizedBaseName, extension, timestamp, counter);

            try (OutputStream outputStream = Files.newOutputStream(
                    targetFile,
                    StandardOpenOption.CREATE_NEW,
                    StandardOpenOption.WRITE);
                 InputStream inputStream = file.getInputStream()) {
                inputStream.transferTo(outputStream);
                outputStream.flush();

                long fileSize = Files.size(targetFile);
                OffsetDateTime storedAt = OffsetDateTime.now();
                LOGGER.info(
                        "Stored scanned document. originalFileName={}, contentType={}, metadata={}, storedFileName={}",
                        originalFileName,
                        validatedContentType,
                        metadata,
                        targetFile.getFileName());
                return new StorageResult(
                        targetFile.getFileName().toString(),
                        targetFile.toString(),
                        validatedContentType,
                        fileSize,
                        storedAt);
            } catch (FileAlreadyExistsException exception) {
                // Reserve the next candidate name atomically instead of overwriting the existing file.
            } catch (IOException exception) {
                deleteQuietly(targetFile);
                LOGGER.error("Failed to store scanned document at {}", targetFile, exception);
                throw new StorageException("Failed to store scanned document.", exception);
            }
        }
    }

    public BackendHealthResponse getStorageHealth() {
        Path targetFolder = resolveTargetFolder();
        boolean writable = Files.isWritable(targetFolder);
        long recentDocumentCount = listRecentDocuments(5).size();

        return new BackendHealthResponse(
                writable ? "UP" : "DEGRADED",
                writable,
                recentDocumentCount);
    }

    public List<StoredDocumentSummary> listRecentDocuments(int limit) {
        Path targetFolder = resolveTargetFolder();
        int boundedLimit = Math.max(1, Math.min(limit, 50));

        try (Stream<Path> pathStream = Files.list(targetFolder)) {
            return pathStream
                    .filter(Files::isRegularFile)
                    .sorted(Comparator.comparing(this::readLastModifiedSafely).reversed())
                    .limit(boundedLimit)
                    .map(this::toStoredDocumentSummary)
                    .toList();
        } catch (IOException exception) {
            throw new StorageException("Failed to list stored scanned documents.", exception);
        }
    }

    private String validateUpload(MultipartFile file, String originalFileName, String declaredContentType) {
        if (file == null || file.isEmpty()) {
            throw new InvalidUploadException("Uploaded file is empty.");
        }

        if (!StringUtils.hasText(originalFileName)) {
            throw new InvalidUploadException("originalFileName is required.");
        }

        String detectedContentType = detectContentType(file);
        if (!StringUtils.hasText(detectedContentType)) {
            throw new InvalidUploadException("Unsupported file signature. Allowed files: PNG, JPEG, PDF.");
        }

        if (!ALLOWED_CONTENT_TYPES.contains(detectedContentType)) {
            throw new InvalidUploadException("Unsupported contentType. Allowed values: image/png, image/jpeg, application/pdf.");
        }

        if (!StringUtils.hasText(declaredContentType)) {
            return detectedContentType;
        }

        String normalizedContentType = declaredContentType.toLowerCase(Locale.ROOT);
        if (!ALLOWED_CONTENT_TYPES.contains(normalizedContentType)) {
            throw new InvalidUploadException("Unsupported contentType. Allowed values: image/png, image/jpeg, application/pdf.");
        }

        if (!normalizedContentType.equals(detectedContentType)) {
            throw new InvalidUploadException("Declared contentType does not match uploaded file content.");
        }

        return detectedContentType;
    }

    private Path resolveTargetFolder() {
        Path targetFolder = Path.of(storageProperties.getScanFolder()).toAbsolutePath().normalize();

        try {
            Files.createDirectories(targetFolder);
            return targetFolder;
        } catch (IOException exception) {
            throw new StorageException("Target folder is not accessible: " + targetFolder, exception);
        }
    }

    private String sanitizeBaseName(String originalFileName) {
        String cleanedPath = StringUtils.cleanPath(originalFileName);
        String fileName = Path.of(cleanedPath).getFileName().toString();
        int lastDot = fileName.lastIndexOf('.');
        String baseName = lastDot > 0 ? fileName.substring(0, lastDot) : fileName;
        String normalized = INVALID_CHARS.matcher(baseName.replace(' ', '-')).replaceAll("-");
        normalized = normalized.replaceAll("-{2,}", "-").replaceAll("^[.-]+|[.-]+$", "");

        if (!StringUtils.hasText(normalized)) {
            return "scan-" + LocalDateTime.now().format(TIMESTAMP_FORMATTER);
        }

        return normalized;
    }

    private String determineExtension(String contentType) {
        return switch (contentType.toLowerCase(Locale.ROOT)) {
            case "image/png" -> "png";
            case "image/jpeg" -> "jpg";
            case "application/pdf" -> "pdf";
            default -> "bin";
        };
    }

    private String determineContentTypeFromPath(Path path) {
        String fileName = path.getFileName().toString().toLowerCase(Locale.ROOT);
        if (fileName.endsWith(".png")) {
            return "image/png";
        }

        if (fileName.endsWith(".jpg") || fileName.endsWith(".jpeg")) {
            return "image/jpeg";
        }

        if (fileName.endsWith(".pdf")) {
            return "application/pdf";
        }

        return "application/octet-stream";
    }

    private String detectContentType(MultipartFile file) {
        try (InputStream inputStream = file.getInputStream()) {
            byte[] header = inputStream.readNBytes(8);

            if (startsWith(header, (byte) 0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A)) {
                return "image/png";
            }

            if (startsWith(header, (byte) 0xFF, (byte) 0xD8, (byte) 0xFF)) {
                return "image/jpeg";
            }

            if (startsWith(header, 0x25, 0x50, 0x44, 0x46, 0x2D)) {
                return "application/pdf";
            }

            return null;
        } catch (IOException exception) {
            throw new StorageException("Failed to inspect uploaded document.", exception);
        }
    }

    private boolean startsWith(byte[] value, int... expectedPrefix) {
        if (value.length < expectedPrefix.length) {
            return false;
        }

        for (int index = 0; index < expectedPrefix.length; index++) {
            if ((value[index] & 0xFF) != (expectedPrefix[index] & 0xFF)) {
                return false;
            }
        }

        return true;
    }

    private Path buildTargetFilePath(
            Path targetFolder,
            String baseName,
            String extension,
            String timestamp,
            int counter) {
        String candidateName = counter <= 0
                ? baseName + "-" + timestamp + "." + extension
                : baseName + "-" + timestamp + "-" + counter + "." + extension;
        Path candidate = targetFolder.resolve(candidateName).normalize();

        if (!candidate.startsWith(targetFolder)) {
            throw new InvalidUploadException("Invalid target file path.");
        }

        return candidate;
    }

    private void deleteQuietly(Path path) {
        try {
            Files.deleteIfExists(path);
        } catch (IOException ignored) {
            // Preserve the original storage exception.
        }
    }

    private OffsetDateTime readLastModifiedSafely(Path path) {
        try {
            return OffsetDateTime.ofInstant(
                    Files.getLastModifiedTime(path).toInstant(),
                    ZoneId.systemDefault());
        } catch (IOException exception) {
            return OffsetDateTime.MIN;
        }
    }

    private StoredDocumentSummary toStoredDocumentSummary(Path path) {
        try {
            return new StoredDocumentSummary(
                    path.getFileName().toString(),
                    determineContentTypeFromPath(path),
                    Files.size(path),
                    readLastModifiedSafely(path));
        } catch (IOException exception) {
            throw new StorageException("Failed to inspect stored scanned document: " + path, exception);
        }
    }
}
