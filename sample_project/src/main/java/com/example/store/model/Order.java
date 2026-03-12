package com.example.store.model;

import javax.persistence.Entity;
import javax.persistence.Id;
import javax.persistence.ManyToMany;
import java.util.List;

@Entity
public class Order {

    @Id
    private Long id;

    private String username;
    private String status;

    // PROBLEMA: @ManyToMany sem FetchType.EAGER e sem @JsonIgnoreProperties
    // → aciona LAZY_LOADING: serialização JSON pode causar LazyInitializationException
    @ManyToMany
    private List<Product> products;

    // getters/setters omitidos para brevidade
}
