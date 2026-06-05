import { CommonModule } from '@angular/common';
import { Component, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { ButtonModule } from 'primeng/button';
import { CardModule } from 'primeng/card';
import { InputTextModule } from 'primeng/inputtext';
import { MessageService } from 'primeng/api';
import { ToastModule } from 'primeng/toast';
import { ProgressBarModule } from 'primeng/progressbar';
import { PipelineApiService } from '../pipeline-api.service';
import { QueryRequest, QueryResult, DocumentDetails } from '../models';

interface ChunkDetail {
  chunk_id: string;
  document_id: string;
  page: number;
  text: string;
  bbox: [number, number, number, number]; // [x1, y1, x2, y2]
  block_ids: string[];
  block_bboxes?: [number, number, number, number][];
  contains_image_ocr: boolean;
  token_count: number;
}

@Component({
  selector: 'app-query-page',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    ButtonModule,
    CardModule,
    InputTextModule,
    ToastModule,
    ProgressBarModule
  ],
  templateUrl: './query-page.component.html',
  styleUrls: ['./query-page.component.css']
})
export class QueryPageComponent implements OnInit {
  queryText = '';
  topK = 50;
  rerankTopN = 5;

  isLoading = false;
  queryResult: QueryResult | null = null;
  errorMessage = '';

  // Selected document for viewing
  selectedDocument: DocumentDetails | null = null;
  isDocumentViewerOpen = false;
  selectedChunkDetail: ChunkDetail | null = null;
  highlightedImageUrl: string | null = null;

  constructor(
    private readonly pipelineApiService: PipelineApiService,
    private readonly messageService: MessageService,
    private readonly router: Router
  ) { }

  ngOnInit(): void {
  }

  onQuery(): void {
    if (!this.queryText.trim()) {
      this.messageService.add({
        severity: 'warn',
        summary: 'Warning',
        detail: 'Please enter a query text'
      });
      return;
    }

    this.isLoading = true;
    this.errorMessage = '';
    this.queryResult = null;
    this.selectedDocument = null;

    const request: QueryRequest = {
      queryText: this.queryText,
      topK: this.topK,
      rerankTopN: this.rerankTopN
    };

    this.pipelineApiService.queryDocuments(request).subscribe({
      next: (result) => {
        this.isLoading = false;
        this.queryResult = result;

        if (result.success) {
          this.messageService.add({
            severity: 'success',
            summary: 'Success',
            detail: `Query completed. Found ${result.totalHits} results, returning ${result.returnedCount}`
          });
        } else {
          this.errorMessage = result.message;
          this.messageService.add({
            severity: 'error',
            summary: 'Error',
            detail: result.message
          });
        }
      },
      error: (error) => {
        this.isLoading = false;
        this.errorMessage = 'Failed to execute query: ' + error.message;
        this.messageService.add({
          severity: 'error',
          summary: 'Error',
          detail: 'Failed to execute query'
        });
      }
    });
  }

  viewDocument(doc: DocumentDetails): void {
    if (this.selectedDocument?.chunkId === doc.chunkId) {
      this.closeDocumentViewer();
      return;
    }

    this.selectedDocument = doc;
    this.isDocumentViewerOpen = true;
    this.highlightedImageUrl = null;
    this.selectedChunkDetail = null;

    // If highlighted text doesn't have yellow highlighting, add it
    if (doc.highlightedText && !doc.highlightedText.includes('background-color')) {
      this.selectedDocument.highlightedText =
        `<span style="background-color: #ffff00; padding: 2px 4px;">${doc.highlightedText}</span>`;
    }

    // Fetch chunk details to get bounding box
    this.pipelineApiService.getChunkDetails(doc.chunkId).subscribe({
      next: (response) => {
        if (response.success && response.chunk) {
          this.selectedChunkDetail = response.chunk as ChunkDetail;

          // Fetch the document image and draw highlight
          this.loadAndHighlightImage(doc.documentId, response.chunk as ChunkDetail);
        }
      },
      error: (error) => {
        console.error('Failed to fetch chunk details:', error);
        // Still show the document without highlighting - using proxy URL
        this.highlightedImageUrl = `/api/documents/document/${doc.documentId}`;
      }
    });
  }

  private loadAndHighlightImage(documentId: string, chunkDetail: ChunkDetail): void {
    const imageUrl = `/api/documents/document/${documentId}`;
    console.log('[QueryPage] Loading image:', imageUrl);

    const img = new Image();
    img.crossOrigin = 'anonymous';
    
    img.onload = () => {
      console.log('[QueryPage] Image loaded successfully:', img.width, 'x', img.height);
      
      try {
        // Create canvas and draw image with highlight
        const canvas = document.createElement('canvas');
        canvas.width = img.width;
        canvas.height = img.height;

        const ctx = canvas.getContext('2d');
        if (!ctx || !chunkDetail.bbox || chunkDetail.bbox.length < 4) {
          console.warn('[QueryPage] Missing context or bbox, showing raw image');
          this.highlightedImageUrl = imageUrl;
          return;
        }

        // Draw the original image
        ctx.drawImage(img, 0, 0);

        // Determine which bboxes to draw (individual lines or the whole block)
        const boxesToDraw = (chunkDetail.block_bboxes && chunkDetail.block_bboxes.length > 0) 
          ? chunkDetail.block_bboxes 
          : [chunkDetail.bbox];

        console.log(`[QueryPage] Drawing ${boxesToDraw.length} highlights`);

        // Set styles for highlights
        ctx.fillStyle = 'rgba(255, 255, 0, 0.3)';
        ctx.strokeStyle = '#FFD700';
        ctx.lineWidth = Math.max(2, img.width / 500);

        for (const box of boxesToDraw) {
          const [x1, y1, x2, y2] = box;
          ctx.fillRect(x1, y1, x2 - x1, y2 - y1);
          ctx.strokeRect(x1, y1, x2 - x1, y2 - y1);
        }

        // Convert canvas to Data URL (synchronous is more reliable for Change Detection)
        const dataUrl = canvas.toDataURL('image/png');
        console.log('[QueryPage] Generated highlighted image URL (length:', dataUrl.length, ')');
        
        // Clean up previous blob URL if it was used
        if (this.highlightedImageUrl && this.highlightedImageUrl.startsWith('blob:')) {
          URL.revokeObjectURL(this.highlightedImageUrl);
        }
        
        this.highlightedImageUrl = dataUrl;

      } catch (err) {
        console.error('[QueryPage] Error processing canvas:', err);
        this.highlightedImageUrl = imageUrl;
      }
    };

    img.onerror = (err) => {
      console.error('[QueryPage] Failed to load image from URL:', imageUrl, err);
      this.highlightedImageUrl = imageUrl;
    };

    img.src = imageUrl;
  }

  closeDocumentViewer(): void {
    this.isDocumentViewerOpen = false;
    this.selectedDocument = null;
    this.selectedChunkDetail = null;
    this.highlightedImageUrl = null;
  }

  goToScanPage(): void {
    this.router.navigate(['/']);
  }
}