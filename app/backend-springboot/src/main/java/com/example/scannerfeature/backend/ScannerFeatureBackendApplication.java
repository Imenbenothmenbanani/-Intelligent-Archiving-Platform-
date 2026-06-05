package com.example.scannerfeature.backend;

import com.example.scannerfeature.backend.config.StorageProperties;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

@SpringBootApplication
@EnableConfigurationProperties(StorageProperties.class)
public class ScannerFeatureBackendApplication {

    public static void main(String[] args) {
        SpringApplication.run(ScannerFeatureBackendApplication.class, args);
    }
}
