package com.example.store.service;

import com.example.store.model.Product;
import com.example.store.repository.ProductRepository;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@RestController
public class ProductService {

    private final ProductRepository productRepository;

    public ProductService(ProductRepository productRepository) {
        this.productRepository = productRepository;
    }

    // PROBLEMA: @GetMapping sem @Cacheable em método getAll*
    // → aciona MISSING_CACHE: resultado estático, deve usar @Cacheable("products")
    @GetMapping("/products")
    public List<Product> getAllProducts() {
        return productRepository.findAll();
    }

    // PROBLEMA: @GetMapping sem @Cacheable em método listAll*
    // → aciona MISSING_CACHE: catálogo raramente muda, candidato a cache
    @GetMapping("/catalog")
    public List<Product> listAll() {
        return productRepository.findAll();
    }
}
