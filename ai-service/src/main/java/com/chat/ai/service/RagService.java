package com.chat.ai.service;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.ai.document.Document;
import org.springframework.ai.reader.TextReader;
import org.springframework.ai.reader.pdf.PagePdfDocumentReader;
import org.springframework.ai.transformer.splitter.TokenTextSplitter;
import org.springframework.ai.vectorstore.VectorStore;
import org.springframework.core.io.FileSystemResource;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;
import reactor.core.publisher.Mono;

import java.io.BufferedReader;
import java.io.File;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

@Slf4j
@Service
@RequiredArgsConstructor
public class RagService {

    private final VectorStore vectorStore;

    public Mono<Integer> uploadAndIndexDocument(MultipartFile multipartFile) {
        String filename = multipartFile.getOriginalFilename();
        if (filename == null) {
            filename = multipartFile.getName();
        }
        final String finalFilename = filename;
        String lowerName = filename.toLowerCase();
        
        if (!lowerName.endsWith(".txt") && !lowerName.endsWith(".pdf")) {
            return Mono.error(new IllegalArgumentException(
                "仅支持 .txt 和 .pdf 格式的文件，当前文件: " + filename
            ));
        }

        try {
            Path tempDir = Files.createTempDirectory("rag-upload-");
            Path tempFilePath = tempDir.resolve(finalFilename);
            multipartFile.transferTo(tempFilePath);
            File tempFile = tempFilePath.toFile();
            
            log.info("文件已保存到临时路径: {}, 大小: {} bytes", tempFilePath, tempFile.length());
            
            return Mono.fromCallable(() -> {
                int result = processDocumentFile(tempFile, finalFilename, tempDir);
                deleteDirectory(tempDir.toFile());
                return result;
            });
        } catch (IOException e) {
            return Mono.error(e);
        }
    }

    private int processDocumentFile(File tempFile, String filename, Path tempDir) {
        List<Document> rawDocuments = readDocuments(tempFile, filename, tempDir);
        log.info("从文件 [{}] 中读取到 {} 个原始文档片段", filename, rawDocuments.size());

        if (rawDocuments.isEmpty()) {
            log.warn("文件 [{}] 内容为空，跳过处理", filename);
            return 0;
        }

        TokenTextSplitter splitter = new TokenTextSplitter();
        List<Document> splitDocuments = splitter.apply(rawDocuments);
        log.info("切分后生成 {} 个文档块（Chunk）", splitDocuments.size());

        for (int i = 0; i < splitDocuments.size(); i++) {
            Document doc = splitDocuments.get(i);
            doc.getMetadata().putIfAbsent("source_file", filename);
            doc.getMetadata().putIfAbsent("chunk_index", i);
            log.debug("Chunk[{}]: content length={}, metadata={}", 
                i, doc.getContent().length(), doc.getMetadata());
        }

        vectorStore.add(splitDocuments);
        log.info("成功将 {} 个文档块写入 VectorStore", splitDocuments.size());

        return splitDocuments.size();
    }

    private List<Document> readDocuments(File file, String filename, Path tempDir) {
        String lowerName = filename.toLowerCase();

        if (lowerName.endsWith(".pdf")) {
            log.info("检测到PDF文件，尝试使用 PagePdfDocumentReader 读取: {}", filename);
            try {
                PagePdfDocumentReader pdfReader = new PagePdfDocumentReader(
                    new FileSystemResource(file)
                );
                List<Document> documents = pdfReader.get();
                
                if (!documents.isEmpty()) {
                    log.info("PagePdfDocumentReader 成功读取 {} 个文档片段", documents.size());
                    return documents;
                }
                
                log.info("PagePdfDocumentReader 读取到 0 个文档，可能是扫描版PDF，尝试OCR...");
                return readPdfWithOcr(file, filename, tempDir);
            } catch (Exception e) {
                log.warn("PagePdfDocumentReader 读取失败，尝试OCR: {}", e.getMessage());
                return readPdfWithOcr(file, filename, tempDir);
            }
        }

        if (lowerName.endsWith(".txt")) {
            log.info("检测到TXT文件，使用 TextReader 读取: {}", filename);
            TextReader textReader = new TextReader(new FileSystemResource(file));
            return textReader.get();
        }

        throw new IllegalArgumentException("不支持的文件格式: " + filename);
    }

    private List<Document> readPdfWithOcr(File pdfFile, String filename, Path tempDir) {
        try {
            Path ocrImageDir = tempDir.resolve("ocr_images");
            Files.createDirectories(ocrImageDir);
            
            String imagePrefix = ocrImageDir.resolve("page").toString();
            
            log.info("正在将PDF转换为图片...");
            ProcessBuilder pdfToPpm = new ProcessBuilder(
                "pdftoppm",
                "-png",
                "-r", "150",
                pdfFile.getAbsolutePath(),
                imagePrefix
            );
            pdfToPpm.redirectErrorStream(true);
            Process pdfProcess = pdfToPpm.start();
            int pdfExitCode = pdfProcess.waitFor();
            
            if (pdfExitCode != 0) {
                String error = readProcessOutput(pdfProcess);
                log.error("pdftoppm 失败: {}", error);
                return List.of();
            }
            
            File[] imageFiles = ocrImageDir.toFile().listFiles((dir, name) -> name.endsWith(".png"));
            if (imageFiles == null || imageFiles.length == 0) {
                log.warn("未生成任何图片文件");
                return List.of();
            }
            
            log.info("生成了 {} 张图片，开始OCR识别...", imageFiles.length);
            
            List<Document> documents = new ArrayList<>();
            StringBuilder allText = new StringBuilder();
            
            java.util.Arrays.sort(imageFiles, (a, b) -> a.getName().compareTo(b.getName()));
            
            for (int i = 0; i < imageFiles.length; i++) {
                File imageFile = imageFiles[i];
                log.info("OCR处理第 {}/{} 页: {}", i + 1, imageFiles.length, imageFile.getName());
                
                String pageText = ocrImage(imageFile);
                if (!pageText.isBlank()) {
                    allText.append(pageText).append("\n\n");
                }
            }
            
            if (!allText.isEmpty()) {
                Document doc = new Document(allText.toString(), Map.of(
                    "source_file", filename,
                    "ocr_processed", "true"
                ));
                documents.add(doc);
                log.info("OCR完成，共提取 {} 字符", allText.length());
            }
            
            return documents;
            
        } catch (Exception e) {
            log.error("OCR处理失败", e);
            return List.of();
        }
    }

    private String ocrImage(File imageFile) throws Exception {
        ProcessBuilder tesseract = new ProcessBuilder(
            "tesseract",
            imageFile.getAbsolutePath(),
            "stdout",
            "-l", "chi_sim+eng"
        );
        tesseract.redirectErrorStream(true);
        
        Process process = tesseract.start();
        StringBuilder result = new StringBuilder();
        
        try (BufferedReader reader = new BufferedReader(
                new InputStreamReader(process.getInputStream(), "UTF-8"))) {
            String line;
            while ((line = reader.readLine()) != null) {
                result.append(line).append("\n");
            }
        }
        
        int exitCode = process.waitFor();
        if (exitCode != 0) {
            log.warn("tesseract 退出码: {}", exitCode);
        }
        
        return result.toString().trim();
    }

    private String readProcessOutput(Process process) throws Exception {
        StringBuilder output = new StringBuilder();
        try (BufferedReader reader = new BufferedReader(
                new InputStreamReader(process.getInputStream()))) {
            String line;
            while ((line = reader.readLine()) != null) {
                output.append(line).append("\n");
            }
        }
        return output.toString();
    }

    private void deleteDirectory(File directory) {
        if (directory.exists()) {
            File[] files = directory.listFiles();
            if (files != null) {
                for (File file : files) {
                    if (file.isDirectory()) {
                        deleteDirectory(file);
                    } else {
                        file.delete();
                    }
                }
            }
            directory.delete();
            log.debug("临时目录已清理: {}", directory.getAbsolutePath());
        }
    }
}
