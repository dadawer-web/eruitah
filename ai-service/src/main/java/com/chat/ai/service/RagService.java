package com.chat.ai.service;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.ai.document.Document;
import org.springframework.ai.reader.TextReader;
import org.springframework.ai.reader.pdf.PagePdfDocumentReader;
import org.springframework.ai.transformer.splitter.TokenTextSplitter;
import org.springframework.ai.vectorstore.VectorStore;
import org.springframework.core.io.FileSystemResource;
import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.core.io.buffer.DataBufferUtils;
import org.springframework.core.io.buffer.DefaultDataBufferFactory;
import org.springframework.http.codec.multipart.FilePart;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

import java.io.File;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.List;
import java.util.Map;

@Slf4j
@Service
@RequiredArgsConstructor
public class RagService {

    private final VectorStore vectorStore;

    public Mono<Integer> uploadAndIndexDocument(FilePart filePart) {
        String filename = filePart.filename();
        String lowerName = filename.toLowerCase();
        
        if (!lowerName.endsWith(".txt") && !lowerName.endsWith(".pdf")) {
            return Mono.error(new IllegalArgumentException(
                "仅支持 .txt 和 .pdf 格式的文件，当前文件: " + filename
            ));
        }

        return Mono.fromCallable(() -> Files.createTempDirectory("rag-upload-"))
            .flatMap(tempDir -> {
                Path tempFilePath = tempDir.resolve(filename);
                File tempFile = tempFilePath.toFile();

                return filePart.transferTo(tempFile)
                    .then(Mono.fromCallable(() -> {
                        log.info("文件已保存到临时路径: {}, 大小: {} bytes", tempFilePath, tempFile.length());
                        
                        List<Document> rawDocuments = readDocuments(tempFile, filename);
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
                    }))
                    .doFinally(signalType -> {
                        boolean deleted = tempFile.delete();
                        log.debug("临时文件删除: {}", deleted ? "成功" : "失败");
                        try {
                            Files.deleteIfExists(tempDir);
                        } catch (IOException e) {
                            log.warn("临时目录删除失败: {}", e.getMessage());
                        }
                    });
            });
    }

    private List<Document> readDocuments(File file, String filename) {
        String lowerName = filename.toLowerCase();

        if (lowerName.endsWith(".pdf")) {
            log.info("检测到PDF文件，使用 PagePdfDocumentReader 读取: {}", filename);
            PagePdfDocumentReader pdfReader = new PagePdfDocumentReader(
                new FileSystemResource(file)
            );
            return pdfReader.get();
        }

        if (lowerName.endsWith(".txt")) {
            log.info("检测到TXT文件，使用 TextReader 读取: {}", filename);
            TextReader textReader = new TextReader(new FileSystemResource(file));
            return textReader.get();
        }

        throw new IllegalArgumentException("不支持的文件格式: " + filename);
    }
}
