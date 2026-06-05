package com.example.scannerfeature.backend.pipeline.request;

import lombok.Data;

@Data
public class OCRConfig {
    private boolean useDocOrientationClassify = true;
    private boolean useDocUnwarping = true;
    private boolean useLayoutDetection = true;
    private boolean useOcrForImageBlock = false;
    private boolean formatBlockContent = true;
    private boolean mergeTables = false;
}
