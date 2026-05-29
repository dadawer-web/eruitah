#!/usr/bin/env node
/**
 * DOCX到HTML转换器
 * 使用mammoth.js将DOCX文件转换为HTML
 */

const mammoth = require('mammoth');
const fs = require('fs');
const path = require('path');

// 获取命令行参数
const args = process.argv.slice(2);

if (args.length < 1) {
    console.error('使用方法: node docx_to_html_converter.js <docx_file_path> [output_html_path]');
    process.exit(1);
}

const docxFilePath = args[0];
const outputHtmlPath = args[1];

// 检查文件是否存在
if (!fs.existsSync(docxFilePath)) {
    console.error(`错误: 文件不存在: ${docxFilePath}`);
    process.exit(1);
}

// mammoth选项配置
const options = {
    styleMap: [
        // 保持表格样式
        "p[style-name='Normal'] => p:fresh",
        "p[style-name='Heading 1'] => h1:fresh",
        "p[style-name='Heading 2'] => h2:fresh",
        "p[style-name='Heading 3'] => h3:fresh",
        // 表格样式映射，添加边框
        "table => table.docx-table[border='1']"
    ],
    includeDefaultStyleMap: true,
    convertImage: mammoth.images.imgElement(function(image) {
        return image.read("base64").then(function(imageBuffer) {
            return {
                src: "data:" + image.contentType + ";base64," + imageBuffer
            };
        });
    })
};

// 转换DOCX到HTML
mammoth.convertToHtml({ path: docxFilePath }, options)
    .then(function(result) {
        let html = result.value; // 生成的HTML
        const messages = result.messages; // 转换过程中的警告和错误信息

        // 为所有表格添加边框属性
        html = html.replace(/<table([^>]*)>/gi, function(match, attributes) {
            // 如果已经有border属性，就不重复添加
            if (attributes.indexOf('border') === -1) {
                return '<table' + attributes + ' border="1">';
            }
            return match;
        });

        // 如果有警告或错误信息，输出到stderr
        if (messages.length > 0) {
            console.error('转换警告/错误:');
            messages.forEach(function(message) {
                console.error(`- ${message.type}: ${message.message}`);
            });
        }

        // 如果指定了输出文件路径，则写入文件
        if (outputHtmlPath) {
            fs.writeFileSync(outputHtmlPath, html, 'utf8');
            console.log(`HTML已保存到: ${outputHtmlPath}`);
        } else {
            // 否则输出到stdout
            console.log(html);
        }
    })
    .catch(function(error) {
        console.error('转换失败:', error);
        process.exit(1);
    });
