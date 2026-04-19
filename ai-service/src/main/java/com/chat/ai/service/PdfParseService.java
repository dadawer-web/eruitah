package com.chat.ai.service;

import lombok.extern.slf4j.Slf4j;
import org.springframework.ai.document.Document;
import org.springframework.ai.reader.pdf.PagePdfDocumentReader;
import org.springframework.ai.reader.pdf.config.PdfDocumentReaderConfig;
import org.springframework.core.io.FileSystemResource;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;

import java.io.File;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Collectors;

@Slf4j
@Service
public class PdfParseService {

    public String parsePdf(MultipartFile file) throws IOException {
        Path tempDir = Files.createTempDirectory("pdf_upload_");
        Path tempFile = tempDir.resolve(file.getOriginalFilename());
        file.transferTo(tempFile.toFile());

        try {
            return parsePdfFile(tempFile.toFile());
        } finally {
            Files.deleteIfExists(tempFile);
            Files.deleteIfExists(tempDir);
        }
    }

    public String parsePdfFile(File file) {
        try {
            PagePdfDocumentReader pdfReader = new PagePdfDocumentReader(
                new FileSystemResource(file),
                PdfDocumentReaderConfig.builder()
                    .withPageTopMargin(0)
                    .withPageBottomMargin(0)
                    .build()
            );

            List<Document> documents = pdfReader.get();

            String content = documents.stream()
                .map(doc -> {
                    String text = doc.getContent();
                    String page = doc.getMetadata().get("page_number") != null 
                        ? "\n\n--- 第 " + doc.getMetadata().get("page_number") + " 页 ---\n\n" 
                        : "";
                    return page + text;
                })
                .collect(Collectors.joining("\n"));

            log.info("PDF解析完成: {} 个文档块, 总字符数: {}", documents.size(), content.length());
            return content;

        } catch (Exception e) {
            log.error("PDF解析失败", e);
            throw new RuntimeException("PDF解析失败: " + e.getMessage());
        }
    }
}
