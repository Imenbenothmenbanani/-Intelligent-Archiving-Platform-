package com.example.scannerfeature.backend.config;

import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.storage")
public class StorageProperties {

    @NotBlank
    private String scanFolder = "C:/app/scanned-documents";
    
    @NotBlank
    private String docsBucket = "docs";
    
    @NotBlank
    private String chunksBucket = "chunks";

    public String getScanFolder() {
        return scanFolder;
    }

    public void setScanFolder(String scanFolder) {
        this.scanFolder = scanFolder;
    }
    
    public String getDocsBucket() {
        return docsBucket;
    }
    
    public void setDocsBucket(String docsBucket) {
        this.docsBucket = docsBucket;
    }
    
    public String getChunksBucket() {
        return chunksBucket;
    }
    
    public void setChunksBucket(String chunksBucket) {
        this.chunksBucket = chunksBucket;
    }
}
